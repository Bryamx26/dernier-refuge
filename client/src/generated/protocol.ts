// AUTO-GÉNÉRÉ par tools/codegen/generate.py depuis shared/protocol/protocol.json. Ne pas modifier.

export const PROTOCOL_VERSION = 1;

/** Codes d'erreur renvoyés dans le message `error`. */
export type ErrorCode = "bad_message" | "unknown_type" | "rate_limited" | "internal";

/** Mesure de latence, envoyé environ une fois par seconde. */
export interface PingPayload {
  /** Horodatage client en millisecondes (performance.now()). */
  readonly client_time: number;
}

/** Premier message après l'ouverture du WebSocket. */
export interface WelcomePayload {
  readonly protocol_version: number;
  readonly zone_id: string;
  readonly character_id: string;
  /** Ticks de simulation par seconde. */
  readonly tick_rate: number;
  /** Horodatage serveur en millisecondes. */
  readonly server_time: number;
}

/** Réponse à `ping`. */
export interface PongPayload {
  readonly client_time: number;
  readonly server_time: number;
}

/** Message refusé ou erreur interne. La connexion reste ouverte sauf mention contraire. */
export interface ErrorPayload {
  readonly code: ErrorCode;
  readonly message: string;
}

export interface ClientPayloads {
  ping: PingPayload;
}

export type ClientMessageType = keyof ClientPayloads;

export interface ServerPayloads {
  welcome: WelcomePayload;
  pong: PongPayload;
  error: ErrorPayload;
}

export type ServerMessageType = keyof ServerPayloads;

/** Message client : `seq` croît à chaque envoi. */
export type ClientMessage = {
  [K in ClientMessageType]: { t: K; seq: number; d: ClientPayloads[K] };
}[ClientMessageType];

/** Message serveur : `tick` = tick de simulation au moment de l'envoi. */
export type ServerMessage = {
  [K in ServerMessageType]: { t: K; seq: number; tick: number; d: ServerPayloads[K] };
}[ServerMessageType];

export const SERVER_MESSAGE_TYPES: readonly ServerMessageType[] = ["welcome", "pong", "error"];
