// Client REST typé. Toutes les routes sont relatives à `/api` (proxy Vite en développement).
import { ApiError, extractDetail } from './errors';
import type { AccountOut, CharacterOut, Credentials, JoinZoneOut, TokenOut, ZoneOut } from './types';

export interface ApiClientOptions {
  /** Préfixe des routes, `/api` par défaut. */
  readonly baseUrl?: string;
  /** Implémentation de fetch (injectable pour les tests). */
  readonly fetchFn?: typeof fetch;
  /** Jeton d'accès courant, lu à chaque requête authentifiée. */
  readonly getToken?: () => string | null;
  /** Appelé quand une requête authentifiée reçoit un 401 (jeton expiré ou révoqué). */
  readonly onUnauthorized?: () => void;
}

export interface ApiClient {
  register: (credentials: Credentials) => Promise<AccountOut>;
  login: (credentials: Credentials) => Promise<TokenOut>;
  me: () => Promise<AccountOut>;
  listCharacters: () => Promise<CharacterOut[]>;
  createCharacter: (name: string) => Promise<CharacterOut>;
  listZones: () => Promise<ZoneOut[]>;
  joinZone: (zoneId: string, characterId: string) => Promise<JoinZoneOut>;
}

interface RequestOptions {
  readonly method?: 'GET' | 'POST';
  readonly body?: unknown;
  readonly auth?: boolean;
}

export function createApiClient(options: ApiClientOptions = {}): ApiClient {
  const baseUrl = options.baseUrl ?? '/api';
  // Liaison explicite : appeler `fetch` détaché de `window` lève « Illegal invocation ».
  const fetchFn = options.fetchFn ?? ((input, init) => fetch(input, init));
  const getToken = options.getToken ?? (() => null);

  async function request<T>(
    path: string,
    { method = 'GET', body, auth = true }: RequestOptions = {},
  ): Promise<T> {
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (auth) {
      const token = getToken();
      if (token) headers.Authorization = `Bearer ${token}`;
    }

    let response: Response;
    try {
      response = await fetchFn(`${baseUrl}${path}`, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause);
      throw new ApiError('network', 0, message);
    }

    const text = await response.text();
    let parsed: unknown = null;
    let parseFailed = false;
    if (text.length > 0) {
      try {
        parsed = JSON.parse(text);
      } catch {
        parseFailed = true;
      }
    }

    if (!response.ok) {
      if (auth && response.status === 401) options.onUnauthorized?.();
      throw new ApiError('http', response.status, extractDetail(parsed) ?? response.statusText);
    }
    if (parseFailed || parsed === null) {
      throw new ApiError('invalid_response', response.status, 'Réponse illisible du serveur');
    }
    // Le serveur est la source de vérité du schéma (OpenAPI) : on fait confiance à la forme reçue.
    return parsed as T;
  }

  return {
    register: (credentials) => request('/auth/register', { method: 'POST', body: credentials, auth: false }),
    login: (credentials) => request('/auth/login', { method: 'POST', body: credentials, auth: false }),
    me: () => request('/auth/me'),
    listCharacters: () => request('/characters'),
    createCharacter: (name) => request('/characters', { method: 'POST', body: { name } }),
    listZones: () => request('/zones'),
    joinZone: (zoneId, characterId) =>
      request(`/zones/${encodeURIComponent(zoneId)}/join`, {
        method: 'POST',
        body: { character_id: characterId },
      }),
  };
}
