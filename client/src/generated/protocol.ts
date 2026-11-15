// AUTO-GÉNÉRÉ par tools/codegen/generate.py depuis shared/protocol/protocol.json. Ne pas modifier.

export const PROTOCOL_VERSION = 3;

/** Codes d'erreur renvoyés dans le message `error`. */
export type ErrorCode = "bad_message" | "unknown_type" | "rate_limited" | "internal";

/** État d'animation d'une entité. */
export type AnimState = "idle" | "walk" | "run" | "attack" | "dead";

/** Nature d'une entité : joueur, zombie ou objet au sol. */
export type EntityKind = "player" | "zombie" | "item";

/** État d'une entité visible dans un snapshot. Positions en tuiles, angle en radians. */
export interface EntityState {
  readonly id: string;
  readonly kind: EntityKind;
  /** Nom du joueur, type de zombie ou nom de l'objet au sol. */
  readonly name: string;
  readonly x: number;
  readonly y: number;
  /** Orientation en radians (0 = vers la droite, sens horaire écran). */
  readonly aim: number;
  readonly anim: AnimState;
  /** Santé relative, de 0 (mort) à 1. */
  readonly health: number;
}

/** Catégorie d'objet. */
export type ItemKind = "melee" | "firearm" | "ammo" | "food" | "drink" | "medical";

/** Un emplacement occupé de l'inventaire. */
export interface InventorySlot {
  /** Index de l'emplacement. */
  readonly slot: number;
  /** Identifiant de l'objet (content/items.yaml). */
  readonly item: string;
  readonly name: string;
  readonly kind: ItemKind;
  readonly qty: number;
  /** Poids de la pile, en kg. */
  readonly weight: number;
  /** Usure restante de 0 à 1 (1 pour un objet sans usure). */
  readonly durability: number;
  /** Munitions dans le chargeur (armes à feu, 0 sinon). */
  readonly loaded: number;
}

/** Effet visuel ponctuel. */
export type FxKind = "shot" | "swing" | "hit" | "blood" | "search";

/** Effet visuel : de (x, y) vers (x2, y2) pour un tir, au point (x, y) sinon. */
export interface FxEvent {
  readonly kind: FxKind;
  readonly x: number;
  readonly y: number;
  readonly x2: number;
  readonly y2: number;
}

/** Action ponctuelle du joueur. */
export type ActionKind = "interact" | "use" | "drop" | "reload" | "respawn";

/** Mesure de latence, envoyé environ une fois par seconde. */
export interface PingPayload {
  /** Horodatage client en millisecondes (performance.now()). */
  readonly client_time: number;
}

/** Entrée pour UN pas de simulation (1/tick_rate s). Envoyé à tick_rate Hz. Le `seq` de l'enveloppe sert de numéro d'entrée pour la réconciliation. */
export interface InputPayload {
  /** Axe horizontal, -1 (gauche) à 1 (droite). */
  readonly move_x: number;
  /** Axe vertical, -1 (haut) à 1 (bas). */
  readonly move_y: number;
  /** Orientation souhaitée en radians. */
  readonly aim: number;
  readonly sprint: boolean;
  /** Gâchette (clic gauche) tenue pendant ce pas. */
  readonly attack: boolean;
}

/** Action ponctuelle, traitée au tick suivant : fouiller/ramasser (interact), utiliser ou équiper l'emplacement `slot` (use), le jeter (drop), recharger (reload), réapparaître après la mort (respawn). */
export interface ActionPayload {
  readonly kind: ActionKind;
  /** Emplacement visé (use, drop), -1 sinon. */
  readonly slot: number;
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

/** État du personnage, envoyé à chaque changement et au moins deux fois par seconde. */
export interface VitalsPayload {
  readonly health: number;
  readonly max_health: number;
  /** 0 (affamé) à 100 (rassasié). */
  readonly hunger: number;
  /** 0 (assoiffé) à 100 (désaltéré). */
  readonly thirst: number;
  readonly bleeding: boolean;
  readonly dead: boolean;
  /** Action longue en cours (« Fouille : Pharmacie », « Rechargement »), vide sinon. */
  readonly action: string;
  /** Avancement de l'action longue, de 0 à 1. */
  readonly action_progress: number;
}

/** Inventaire complet du joueur, envoyé à chaque changement. */
export interface InventoryPayload {
  readonly slots: Array<InventorySlot>;
  /** Nombre d'emplacements. */
  readonly capacity: number;
  /** Emplacement de l'arme en main, -1 : mains nues. */
  readonly equipped: number;
  readonly weight: number;
  readonly max_weight: number;
}

/** Effets visuels du tick, autour du joueur. */
export interface FxPayload {
  readonly events: Array<FxEvent>;
}

/** Message court affiché au joueur (butin, inventaire plein…). */
export interface NoticePayload {
  readonly text: string;
}

/** Message refusé ou erreur interne. La connexion reste ouverte sauf mention contraire. */
export interface ErrorPayload {
  readonly code: ErrorCode;
  readonly message: string;
}

export interface ClientPayloads {
  ping: PingPayload;
  input: InputPayload;
  action: ActionPayload;
}

export type ClientMessageType = keyof ClientPayloads;

export interface ServerPayloads {
  welcome: WelcomePayload;
  snapshot: SnapshotPayload;
  pong: PongPayload;
  vitals: VitalsPayload;
  inventory: InventoryPayload;
  fx: FxPayload;
  notice: NoticePayload;
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

export const SERVER_MESSAGE_TYPES: readonly ServerMessageType[] = ["welcome", "snapshot", "pong", "vitals", "inventory", "fx", "notice", "error"];
