// Instance partagée du client REST, branchée sur le store de session.
import { useSessionStore } from '../state/sessionStore';
import { createApiClient } from './client';

export const api = createApiClient({
  getToken: () => useSessionStore.getState().token,
  onUnauthorized: () => useSessionStore.getState().logout(),
});
