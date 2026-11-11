// Session joueur : jeton d'accès (persisté en sessionStorage) et compte courant.
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import type { AccountOut } from '../api/types';

export interface SessionState {
  readonly token: string | null;
  readonly account: AccountOut | null;
  setToken: (token: string) => void;
  setAccount: (account: AccountOut) => void;
  logout: () => void;
}

export const SESSION_STORAGE_KEY = 'dernier-refuge.session';

export const useSessionStore = create<SessionState>()(
  persist(
    (set) => ({
      token: null,
      account: null,
      // Un nouveau jeton invalide le compte en cache : il sera relu via /auth/me.
      setToken: (token) => set({ token, account: null }),
      setAccount: (account) => set({ account }),
      logout: () => set({ token: null, account: null }),
    }),
    {
      name: SESSION_STORAGE_KEY,
      storage: createJSONStorage(() => sessionStorage),
      // Seul le jeton est persisté ; le compte est relu au chargement.
      partialize: (state) => ({ token: state.token }),
    },
  ),
);
