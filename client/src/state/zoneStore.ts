// Connexion à la zone courante : un ZoneSocket et son état observé par l'interface.
import { create } from 'zustand';
import { ZoneClient } from '../net/ZoneClient';
import { ZoneSocket, type ZoneSocketOptions, type ZoneSocketStatus } from '../net/ZoneSocket';
import { useGameStore } from './gameStore';

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
  /** Logique de jeu réseau (entrées, prédiction, interpolation), passée à Phaser par le bridge. */
  readonly client: ZoneClient | null;
  connect: (params: ConnectParams) => void;
  /** Ferme la liaison et quitte l'écran de jeu. */
  leave: () => void;
}

/** Fabrique de sockets remplaçable dans les tests. */
let socketFactory = (options: ZoneSocketOptions): ZoneSocket => new ZoneSocket(options);
export function setZoneSocketFactory(factory: (options: ZoneSocketOptions) => ZoneSocket): void {
  socketFactory = factory;
}

let unsubscribe: (() => void)[] = [];

export const useZoneStore = create<ZoneState>()((set, get) => ({
  session: null,
  status: null,
  socket: null,
  client: null,

  connect: ({ ticket, wsPath, ...session }) => {
    get().leave();
    const socket = socketFactory({ zoneId: session.zoneId, ticket, path: wsPath });
    // Créé avant connect() pour ne manquer ni le welcome ni le premier snapshot.
    const client = new ZoneClient(socket);
    set({ session, socket, client, status: socket.getStatus() });
    const game = useGameStore.getState();
    game.reset();
    unsubscribe = [
      socket.onStatus((status) => set({ status })),
      socket.on('vitals', (m) => game.setVitals(m.d)),
      socket.on('inventory', (m) => game.setInventory(m.d)),
      socket.on('notice', (m) => game.pushNotice(m.d.text)),
    ];
    socket.connect();
  },

  leave: () => {
    unsubscribe.forEach((off) => off());
    unsubscribe = [];
    useGameStore.getState().reset();
    get().client?.dispose();
    get().socket?.close();
    set({ session: null, socket: null, client: null, status: null });
  },
}));
