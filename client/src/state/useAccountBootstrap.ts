// Relit le compte (/auth/me) quand un jeton est présent mais que le compte n'est pas connu.
import { useEffect, useState } from 'react';
import { describeApiError, type ApiClient } from '../api';
import { useSessionStore } from './sessionStore';

export function useAccountBootstrap(api: Pick<ApiClient, 'me'>): { error: string | null; retry: () => void } {
  const token = useSessionStore((s) => s.token);
  const account = useSessionStore((s) => s.account);
  const setAccount = useSessionStore((s) => s.setAccount);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!token || account) return;
    let cancelled = false;
    api
      .me()
      .then((me) => {
        if (!cancelled) {
          setError(null);
          setAccount(me);
        }
      })
      .catch((err: unknown) => {
        // Un 401 déclenche déjà la déconnexion via le client REST.
        if (!cancelled) setError(describeApiError(err, 'characters'));
      });
    return () => {
      cancelled = true;
    };
  }, [api, token, account, setAccount, attempt]);

  return { error, retry: () => setAttempt((n) => n + 1) };
}
