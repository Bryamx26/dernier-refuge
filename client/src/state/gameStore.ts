// État de jeu du personnage affiché par le HUD : jauges, inventaire, messages. Alimenté par les
// messages serveur `vitals`, `inventory` et `notice` (voir zoneStore).
import { create } from 'zustand';
import type { InventoryPayload, VitalsPayload } from '../generated/protocol';

export interface Notice {
  readonly id: number;
  readonly text: string;
  readonly at: number;
}

/** Messages gardés à l'écran, et leur durée d'affichage. */
export const MAX_NOTICES = 4;
export const NOTICE_TTL_MS = 5000;

export interface GameState {
  readonly vitals: VitalsPayload | null;
  readonly inventory: InventoryPayload | null;
  readonly notices: readonly Notice[];
  setVitals: (vitals: VitalsPayload) => void;
  setInventory: (inventory: InventoryPayload) => void;
  pushNotice: (text: string, now?: number) => void;
  /** Retire les messages expirés. */
  pruneNotices: (now?: number) => void;
  reset: () => void;
}

let noticeId = 0;

export const useGameStore = create<GameState>()((set) => ({
  vitals: null,
  inventory: null,
  notices: [],
  setVitals: (vitals) => set({ vitals }),
  setInventory: (inventory) => set({ inventory }),
  pushNotice: (text, now = Date.now()) =>
    set((state) => ({
      notices: [...state.notices, { id: (noticeId += 1), text, at: now }].slice(-MAX_NOTICES),
    })),
  pruneNotices: (now = Date.now()) =>
    set((state) => {
      const kept = state.notices.filter((n) => now - n.at < NOTICE_TTL_MS);
      return kept.length === state.notices.length ? state : { notices: kept };
    }),
  reset: () => set({ vitals: null, inventory: null, notices: [] }),
}));
