// AUTO-GÉNÉRÉ par tools/codegen/generate.py depuis shared/protocol/protocol.json. Ne pas modifier.

export const PROTOCOL_VERSION = 2;

/** Codes d'erreur renvoyés dans le message `error`. */
export type ErrorCode = "bad_message" | "unknown_type" | "rate_limited" | "internal";

/** État d'animation d'une entité. */
export type AnimState = "idle" | "walk" | "run";

/** État d'une entité visible dans un snapshot. Positions en tuiles, angle en radians. */
export interface EntityState {
  readonly id: string;
  readonly kind: "player";
  readonly name: string;
  readonly x: number;
  readonly y: number;
  /** Orientation en radians (0 = vers la droite, sens horaire écran). */
  readonly aim: number;
  readonly anim: AnimState;
}

/** Mesure de latence, envoyé environ une fois par seconde. */
export interface PingPayload {
  /** Horodatage client en millisecondes (performance.now()). */
  readonly client_time: number;
}

/** Entrée de déplacement pour UN pas de simulation (1/tick_rate s). Envoyé à tick_rate Hz. Le `seq` de l'enveloppe sert de numéro d'entrée pour la réconciliation. */
export interface InputPayload {
  /** Axe horizontal, -1 (gauche) à 1 (droite). */
  readonly move_x: number;
  /** Axe vertical, -1 (haut) à 1 (bas). */
  readonly move_y: number;
  /** Orientation souhaitée en radians. */
  readonly aim: number;
  readonly sprint: boolean;
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
  /** Identifiant de l'entité du joueur dans les snapshots. */
  readonly entity_id: string;
  /** Carte de la zone, chargée depuis /game/maps/<map_id>.tmj. */
  readonly map_id: string;
}

/** État des entités proches du joueur, envoyé à chaque tick. Une entité absente du snapshot n'est plus visible. */
export interface SnapshotPayload {
  /** `seq` de la dernière entrée du joueur appliquée par le serveur (0 si aucune). */
  readonly ack_seq: number;
  readonly entities: Array<EntityState>;
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
  input: InputPayload;
}

export type ClientMessageType = keyof ClientPayloads;

export interface ServerPayloads {
  welcome: WelcomePayload;
  snapshot: SnapshotPayload;
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

export const SERVER_MESSAGE_TYPES: readonly ServerMessageType[] = ["welcome", "snapshot", "pong", "error"];
