import { describe, expect, it, vi } from 'vitest';
import { createApiClient } from './client';
import { ApiError } from './errors';
import { describeApiError } from './messages';

function jsonResponse(status: number, body: unknown): Response {
  return new Response(body === undefined ? '' : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function setup(response: Response | Error, token: string | null = 'jwt-123') {
  const fetchFn = vi.fn<typeof fetch>(() =>
    response instanceof Error ? Promise.reject(response) : Promise.resolve(response),
  );
  const onUnauthorized = vi.fn();
  const client = createApiClient({ fetchFn, getToken: () => token, onUnauthorized });
  const call = () => {
    const [url, init] = fetchFn.mock.calls[0] ?? [];
    return { url, init, headers: (init?.headers ?? {}) as Record<string, string> };
  };
  return { client, fetchFn, onUnauthorized, call };
}

describe('client REST', () => {
  it('login : POST JSON sans jeton', async () => {
    const { client, call } = setup(
      jsonResponse(200, { access_token: 'a', token_type: 'bearer', expires_in: 60 }),
    );
    const token = await client.login({ username: 'rodeur', password: 'motdepasse' });
    expect(token.access_token).toBe('a');
    const { url, init, headers } = call();
    expect(url).toBe('/api/auth/login');
    expect(init?.method).toBe('POST');
    expect(init?.body).toBe(JSON.stringify({ username: 'rodeur', password: 'motdepasse' }));
    expect(headers.Authorization).toBeUndefined();
    expect(headers['Content-Type']).toBe('application/json');
  });

  it('me : ajoute le jeton Bearer', async () => {
    const { client, call } = setup(jsonResponse(200, { id: 'u1', username: 'rodeur' }));
    await expect(client.me()).resolves.toEqual({ id: 'u1', username: 'rodeur' });
    expect(call().url).toBe('/api/auth/me');
    expect(call().headers.Authorization).toBe('Bearer jwt-123');
  });

  it('createCharacter, listZones, listCharacters : bonnes routes', async () => {
    const created = { id: 'c1', name: 'Élise', zone_id: 'valcendre', x: 64, y: 64, is_dead: false };
    const a = setup(jsonResponse(201, created));
    await expect(a.client.createCharacter('Élise')).resolves.toEqual(created);
    expect(a.call().url).toBe('/api/characters');
    expect(a.call().init?.body).toBe('{"name":"Élise"}');

    const b = setup(jsonResponse(200, []));
    await b.client.listZones();
    expect(b.call().url).toBe('/api/zones');
    expect(b.call().init?.method).toBe('GET');

    const c = setup(jsonResponse(200, []));
    await c.client.listCharacters();
    expect(c.call().url).toBe('/api/characters');
  });

  it('joinZone : POST /zones/{id}/join avec character_id', async () => {
    const { client, call } = setup(
      jsonResponse(200, { ticket: 't', ws_path: '/ws/zone/valcendre', expires_in: 30 }),
    );
    const join = await client.joinZone('valcendre', 'c1');
    expect(join.ticket).toBe('t');
    expect(call().url).toBe('/api/zones/valcendre/join');
    expect(call().init?.body).toBe('{"character_id":"c1"}');
  });

  it('erreur HTTP typée avec le detail FastAPI', async () => {
    const { client } = setup(jsonResponse(409, { detail: 'Pseudo déjà pris' }));
    const error = await client.register({ username: 'x', password: 'y' }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ kind: 'http', status: 409, detail: 'Pseudo déjà pris' });
    expect(describeApiError(error, 'register')).toBe('Ce pseudo est déjà pris.');
  });

  it('erreur 422 : agrège les messages de validation', async () => {
    const { client } = setup(jsonResponse(422, { detail: [{ msg: 'trop court' }, { msg: 'invalide' }] }));
    await expect(client.createCharacter('A')).rejects.toMatchObject({
      status: 422,
      detail: 'trop court ; invalide',
    });
  });

  it('401 sur une route authentifiée : rappel onUnauthorized', async () => {
    const { client, onUnauthorized } = setup(jsonResponse(401, { detail: 'Authentification requise' }));
    const error = await client.listCharacters().catch((e: unknown) => e);
    expect((error as ApiError).isUnauthorized).toBe(true);
    expect(onUnauthorized).toHaveBeenCalledOnce();
  });

  it('401 sur login : pas de déconnexion forcée', async () => {
    const { client, onUnauthorized } = setup(jsonResponse(401, { detail: 'Identifiants invalides' }));
    const error = await client.login({ username: 'a', password: 'b' }).catch((e: unknown) => e);
    expect(describeApiError(error, 'login')).toBe('Identifiants invalides.');
    expect(onUnauthorized).not.toHaveBeenCalled();
  });

  it('erreur réseau typée', async () => {
    const { client } = setup(new TypeError('Failed to fetch'));
    const error = await client.listZones().catch((e: unknown) => e);
    expect(error).toMatchObject({ kind: 'network', status: 0 });
    expect(describeApiError(error, 'zones')).toMatch(/injoignable/);
  });

  it('réponse 2xx illisible', async () => {
    const { client } = setup(new Response('<html>', { status: 200 }));
    await expect(client.me()).rejects.toMatchObject({ kind: 'invalid_response' });
  });
});
