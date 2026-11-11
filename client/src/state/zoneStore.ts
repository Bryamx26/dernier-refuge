// Connexion à la zone courante : un ZoneSocket et son état observé par l'interface.
import { create } from 'zustand';
import { ZoneSocket, type ZoneSocketOptions, type ZoneSocketStatus } from '../net/ZoneSocket';

export interface ZoneSession {
  readonly zoneId: string;
  readonly zoneName: string;
  readonly characterName: string;
}

export interface ConnectParams extends ZoneSession {
  readonly ticket: string;
  readonly wsPath?: string;
}

export interface ZoneState {
  /** Zone que le joueur a rejointe (reste définie après une fermeture, pour afficher la cause). */
  readonly session: ZoneSession | null;
  readonly status: ZoneSocketStatus | null;
  readonly socket: ZoneSocket | null;
  connect: (params: ConnectParams) => void;
  /** Ferme la liaison et quitte l'écran de jeu. */
  leave: () => void;
}

/** Fabrique de sockets remplaçable dans les tests. */
let socketFactory = (options: ZoneSocketOptions): ZoneSocket => new ZoneSocket(options);
export function setZoneSocketFactory(factory: (options: ZoneSocketOptions) => ZoneSocket): void {
  socketFactory = factory;
}

let unsubscribeStatus: (() => void) | null = null;

export const useZoneStore = create<ZoneState>()((set, get) => ({
  session: null,
  status: null,
  socket: null,

  connect: ({ ticket, wsPath, ...session }) => {
    get().leave();
    const socket = socketFactory({ zoneId: session.zoneId, ticket, path: wsPath });
    set({ session, socket, status: socket.getStatus() });
    unsubscribeStatus = socket.onStatus((status) => set({ status }));
    socket.connect();
  },

  leave: () => {
    unsubscribeStatus?.();
    unsubscribeStatus = null;
    get().socket?.close();
    set({ session: null, socket: null, status: null });
  },
}));
