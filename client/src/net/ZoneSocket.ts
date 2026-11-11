// Connexion WebSocket à une zone : envoi typé, décodage validé, ping périodique et mesure du RTT.
import type {
  ClientMessage,
  ClientMessageType,
  ClientPayloads,
  ErrorPayload,
  ServerMessage,
  ServerMessageType,
  WelcomePayload,
} from '../generated/protocol';
import { decodeServerMessage } from './decode';

export type ZoneSocketState = 'idle' | 'connecting' | 'open' | 'closed';

export interface ZoneSocketStatus {
  readonly state: ZoneSocketState;
  readonly zoneId: string;
  /** RTT lissé (moyenne mobile exponentielle), en millisecondes. */
  readonly rttMs: number | null;
  /** Dernier tick de simulation reçu du serveur. */
  readonly serverTick: number | null;
  readonly welcome: WelcomePayload | null;
  readonly lastError: ErrorPayload | null;
  readonly closeCode: number | null;
  readonly closeReason: string;
}

export type ServerMessageOf<K extends ServerMessageType> = Extract<ServerMessage, { t: K }>;
export type ServerMessageHandler<K extends ServerMessageType> = (message: ServerMessageOf<K>) => void;
export type StatusListener = (status: ZoneSocketStatus) => void;

/** Sous-ensemble de l'API WebSocket utilisé ici (permet un faux WebSocket dans les tests). */
export interface WebSocketLike {
  readonly readyState: number;
  onopen: ((event: Event) => void) | null;
  onmessage: ((event: MessageEvent) => void) | null;
  onclose: ((event: CloseEvent) => void) | null;
  onerror: ((event: Event) => void) | null;
  send(data: string): void;
  close(code?: number, reason?: string): void;
}

export type WebSocketFactory = (url: string) => WebSocketLike;

export interface ZoneSocketOptions {
  readonly zoneId: string;
  readonly ticket: string;
  /** Chemin du WebSocket, `/ws/zone/{zoneId}` par défaut (le serveur le renvoie dans `ws_path`). */
  readonly path?: string;
  /** Origine `ws://hôte` ; déduite de `window.location` par défaut. */
  readonly origin?: string;
  readonly createSocket?: WebSocketFactory;
  /** Horloge en millisecondes, `performance.now()` par défaut. */
  readonly now?: () => number;
  readonly pingIntervalMs?: number;
  /** Poids d'un nouvel échantillon de RTT dans la moyenne lissée (0 < α ≤ 1). */
  readonly rttSmoothing?: number;
}

const WS_OPEN = 1;
const DEFAULT_PING_INTERVAL_MS = 1000;
const DEFAULT_RTT_SMOOTHING = 0.2;

export function defaultWsOrigin(): string {
  const { protocol, host } = window.location;
  return `${protocol === 'https:' ? 'wss:' : 'ws:'}//${host}`;
}

export function buildZoneUrl(origin: string, path: string, ticket: string): string {
  const separator = path.includes('?') ? '&' : '?';
  return `${origin}${path}${separator}ticket=${encodeURIComponent(ticket)}`;
}

export class ZoneSocket {
  private readonly options: Required<Omit<ZoneSocketOptions, 'origin' | 'path'>> & { url: string };
  private socket: WebSocketLike | null = null;
  private pingTimer: ReturnType<typeof setInterval> | null = null;
  private seq = 0;
  private status: ZoneSocketStatus;
  private readonly handlers = new Map<ServerMessageType, Set<(message: ServerMessage) => void>>();
  private readonly statusListeners = new Set<StatusListener>();
  /** Nombre de trames ignorées (JSON invalide, type inconnu, charge utile non conforme). */
  ignoredFrames = 0;

  constructor(options: ZoneSocketOptions) {
    const path = options.path ?? `/ws/zone/${encodeURIComponent(options.zoneId)}`;
    this.options = {
      zoneId: options.zoneId,
      ticket: options.ticket,
      url: buildZoneUrl(options.origin ?? defaultWsOrigin(), path, options.ticket),
      createSocket: options.createSocket ?? ((url) => new WebSocket(url)),
      now: options.now ?? (() => performance.now()),
      pingIntervalMs: options.pingIntervalMs ?? DEFAULT_PING_INTERVAL_MS,
      rttSmoothing: options.rttSmoothing ?? DEFAULT_RTT_SMOOTHING,
    };
    this.status = {
      state: 'idle',
      zoneId: options.zoneId,
      rttMs: null,
      serverTick: null,
      welcome: null,
      lastError: null,
      closeCode: null,
      closeReason: '',
    };
  }

  get url(): string {
    return this.options.url;
  }

  getStatus(): ZoneSocketStatus {
    return this.status;
  }

  /** Ouvre la connexion. Un ZoneSocket ne sert qu'une fois (le ticket est à usage unique). */
  connect(): void {
    if (this.status.state !== 'idle') throw new Error('ZoneSocket déjà utilisé');
    this.updateStatus({ state: 'connecting' });
    const socket = this.options.createSocket(this.options.url);
    this.socket = socket;
    socket.onopen = () => this.handleOpen();
    socket.onmessage = (event) => this.handleFrame(event.data);
    socket.onclose = (event) => this.handleClose(event.code, event.reason);
    // Une erreur est toujours suivie d'un `close` : rien à faire ici.
    socket.onerror = null;
  }

  /** Ferme la connexion côté client. */
  close(code = 1000, reason = 'Déconnexion'): void {
    this.stopPing();
    if (this.socket && this.status.state !== 'closed') {
      this.socket.close(code, reason);
    }
    // On n'attend pas l'accusé du serveur : l'état est fermé immédiatement côté interface.
    this.handleClose(code, reason);
  }

  /** Envoie un message client typé ; `seq` croît à chaque envoi. Renvoie false si la connexion n'est pas ouverte. */
  send<K extends ClientMessageType>(t: K, d: ClientPayloads[K]): boolean {
    const socket = this.socket;
    if (!socket || this.status.state !== 'open' || socket.readyState !== WS_OPEN) return false;
    this.seq += 1;
    const message = { t, seq: this.seq, d } as ClientMessage;
    socket.send(JSON.stringify(message));
    return true;
  }

  /** S'abonne à un type de message serveur. Renvoie la fonction de désabonnement. */
  on<K extends ServerMessageType>(type: K, handler: ServerMessageHandler<K>): () => void {
    let set = this.handlers.get(type);
    if (!set) {
      set = new Set();
      this.handlers.set(type, set);
    }
    const erased = handler as (message: ServerMessage) => void;
    set.add(erased);
    return () => {
      set.delete(erased);
    };
  }

  /** S'abonne aux changements d'état ; l'écouteur reçoit immédiatement l'état courant. */
  onStatus(listener: StatusListener): () => void {
    this.statusListeners.add(listener);
    listener(this.status);
    return () => {
      this.statusListeners.delete(listener);
    };
  }

  private handleOpen(): void {
    if (this.status.state !== 'connecting') return;
    this.updateStatus({ state: 'open' });
    this.sendPing();
    this.pingTimer = setInterval(() => this.sendPing(), this.options.pingIntervalMs);
  }

  private handleFrame(data: unknown): void {
    const message = decodeServerMessage(data);
    if (!message) {
      this.ignoredFrames += 1;
      return;
    }
    const tick = Math.max(this.status.serverTick ?? 0, message.tick);
    switch (message.t) {
      case 'welcome':
        this.updateStatus({ serverTick: tick, welcome: message.d });
        break;
      case 'pong':
        this.updateStatus({ serverTick: tick, rttMs: this.smoothRtt(message.d.client_time) });
        break;
      case 'error':
        this.updateStatus({ serverTick: tick, lastError: message.d });
        break;
    }
    this.handlers.get(message.t)?.forEach((handler) => handler(message));
  }

  private handleClose(code: number, reason: string): void {
    this.stopPing();
    if (this.status.state === 'closed') return;
    if (this.socket) {
      this.socket.onopen = null;
      this.socket.onmessage = null;
      this.socket.onclose = null;
    }
    this.updateStatus({ state: 'closed', closeCode: code, closeReason: reason });
  }

  private sendPing(): void {
    this.send('ping', { client_time: this.options.now() });
  }

  private smoothRtt(clientTime: number): number | null {
    const sample = this.options.now() - clientTime;
    const previous = this.status.rttMs;
    if (!Number.isFinite(sample) || sample < 0) return previous;
    if (previous === null) return sample;
    return previous + this.options.rttSmoothing * (sample - previous);
  }

  private stopPing(): void {
    if (this.pingTimer !== null) {
      clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
  }

  private updateStatus(patch: Partial<ZoneSocketStatus>): void {
    this.status = { ...this.status, ...patch };
    this.statusListeners.forEach((listener) => listener(this.status));
  }
}
