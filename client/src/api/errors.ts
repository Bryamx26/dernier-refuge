// Erreurs typées du client REST.

export type ApiErrorKind =
  /** Le serveur n'a pas pu être joint (réseau, proxy, CORS…). */
  | 'network'
  /** Réponse HTTP non 2xx. */
  | 'http'
  /** Réponse 2xx dont le corps n'est pas du JSON exploitable. */
  | 'invalid_response';

export class ApiError extends Error {
  override readonly name = 'ApiError';

  constructor(
    readonly kind: ApiErrorKind,
    /** Code HTTP (0 pour une erreur réseau). */
    readonly status: number,
    /** Message lisible renvoyé par le serveur (`detail` de FastAPI) ou décrit côté client. */
    readonly detail: string,
  ) {
    super(`${kind} ${status}: ${detail}`);
  }

  get isUnauthorized(): boolean {
    return this.kind === 'http' && this.status === 401;
  }
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError;
}

/** Extrait un message du corps d'erreur FastAPI : `{"detail": "..."}` ou `{"detail": [{"msg": "..."}]}`. */
export function extractDetail(body: unknown): string | null {
  if (typeof body !== 'object' || body === null || !('detail' in body)) return null;
  const detail: unknown = body.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item: unknown) =>
        typeof item === 'object' && item !== null && 'msg' in item && typeof item.msg === 'string'
          ? item.msg
          : null,
      )
      .filter((msg): msg is string => msg !== null);
    return messages.length > 0 ? messages.join(' ; ') : null;
  }
  return null;
}
