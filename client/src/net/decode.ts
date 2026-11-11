// Décodage et validation des messages serveur. Tout message invalide ou de type inconnu est rejeté (null).
import {
  SERVER_MESSAGE_TYPES,
  type AnimState,
  type EntityKind,
  type EntityState,
  type ErrorCode,
  type FxEvent,
  type FxKind,
  type InventorySlot,
  type ItemKind,
  type ServerMessage,
  type ServerMessageType,
  type ServerPayloads,
} from '../generated/protocol';

type UnknownRecord = Record<string, unknown>;

const ERROR_CODES: readonly ErrorCode[] = ['bad_message', 'unknown_type', 'rate_limited', 'internal'];
const ANIM_STATES: readonly AnimState[] = ['idle', 'walk', 'run', 'attack', 'dead'];
const ENTITY_KINDS: readonly EntityKind[] = ['player', 'zombie', 'item'];
const ITEM_KINDS: readonly ItemKind[] = ['melee', 'firearm', 'ammo', 'food', 'drink', 'medical'];
const FX_KINDS: readonly FxKind[] = ['shot', 'swing', 'hit', 'blood', 'search'];

function isOneOf<T extends string>(value: unknown, allowed: readonly T[]): value is T {
  return typeof value === 'string' && (allowed as readonly string[]).includes(value);
}

function isInRange(value: unknown, min: number, max: number): value is number {
  return isFiniteNumber(value) && value >= min && value <= max;
}

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function isNonNegative(value: unknown): value is number {
  return isFiniteNumber(value) && value >= 0;
}

function isIntAtLeast(value: unknown, min: number): value is number {
  return isFiniteNumber(value) && Number.isInteger(value) && value >= min;
}

function isBoundedString(value: unknown, min: number, max: number): value is string {
  return typeof value === 'string' && value.length >= min && value.length <= max;
}

/** Valide une entité de snapshot (EntityState). */
export function isEntityState(value: unknown): value is EntityState {
  return (
    isRecord(value) &&
    isBoundedString(value.id, 1, 64) &&
    isOneOf(value.kind, ENTITY_KINDS) &&
    isBoundedString(value.name, 0, 32) &&
    isFiniteNumber(value.x) &&
    isFiniteNumber(value.y) &&
    isFiniteNumber(value.aim) &&
    isOneOf(value.anim, ANIM_STATES) &&
    isInRange(value.health, 0, 1)
  );
}

export function isInventorySlot(value: unknown): value is InventorySlot {
  return (
    isRecord(value) &&
    isInRange(value.slot, 0, 63) &&
    Number.isInteger(value.slot) &&
    isBoundedString(value.item, 1, 32) &&
    isBoundedString(value.name, 0, 32) &&
    isOneOf(value.kind, ITEM_KINDS) &&
    isIntAtLeast(value.qty, 1) &&
    isNonNegative(value.weight) &&
    isInRange(value.durability, 0, 1) &&
    isIntAtLeast(value.loaded, 0)
  );
}

export function isFxEvent(value: unknown): value is FxEvent {
  return (
    isRecord(value) &&
    isOneOf(value.kind, FX_KINDS) &&
    isFiniteNumber(value.x) &&
    isFiniteNumber(value.y) &&
    isFiniteNumber(value.x2) &&
    isFiniteNumber(value.y2)
  );
}

/** Garde de type sur le discriminant `t`. */
export function isServerMessageType(value: unknown): value is ServerMessageType {
  return typeof value === 'string' && (SERVER_MESSAGE_TYPES as readonly string[]).includes(value);
}

/**
 * Un validateur par type serveur. Le `Record` est exhaustif : ajouter un message dans
 * protocol.json sans validateur ici casse la compilation.
 */
const PAYLOAD_VALIDATORS: {
  [K in ServerMessageType]: (d: UnknownRecord) => d is UnknownRecord & ServerPayloads[K];
} = {
  welcome: (d): d is UnknownRecord & ServerPayloads['welcome'] =>
    isIntAtLeast(d.protocol_version, 1) &&
    isBoundedString(d.zone_id, 1, 64) &&
    isBoundedString(d.character_id, 1, 64) &&
    isIntAtLeast(d.tick_rate, 1) &&
    isNonNegative(d.server_time) &&
    isBoundedString(d.entity_id, 1, 64) &&
    isBoundedString(d.map_id, 1, 64),
  snapshot: (d): d is UnknownRecord & ServerPayloads['snapshot'] =>
    isIntAtLeast(d.ack_seq, 0) && Array.isArray(d.entities) && d.entities.every(isEntityState),
  pong: (d): d is UnknownRecord & ServerPayloads['pong'] =>
    isNonNegative(d.client_time) && isNonNegative(d.server_time),
  vitals: (d): d is UnknownRecord & ServerPayloads['vitals'] =>
    isNonNegative(d.health) &&
    isNonNegative(d.max_health) &&
    isInRange(d.hunger, 0, 100) &&
    isInRange(d.thirst, 0, 100) &&
    typeof d.bleeding === 'boolean' &&
    typeof d.dead === 'boolean' &&
    isBoundedString(d.action, 0, 48) &&
    isInRange(d.action_progress, 0, 1),
  inventory: (d): d is UnknownRecord & ServerPayloads['inventory'] =>
    Array.isArray(d.slots) &&
    d.slots.length <= 64 &&
    d.slots.every(isInventorySlot) &&
    isIntAtLeast(d.capacity, 1) &&
    isIntAtLeast(d.equipped, -1) &&
    isNonNegative(d.weight) &&
    isNonNegative(d.max_weight),
  fx: (d): d is UnknownRecord & ServerPayloads['fx'] =>
    Array.isArray(d.events) && d.events.length <= 128 && d.events.every(isFxEvent),
  notice: (d): d is UnknownRecord & ServerPayloads['notice'] => isBoundedString(d.text, 1, 120),
  error: (d): d is UnknownRecord & ServerPayloads['error'] =>
    typeof d.code === 'string' &&
    (ERROR_CODES as readonly string[]).includes(d.code) &&
    isBoundedString(d.message, 0, 200),
};

/** Valide une valeur déjà désérialisée. */
export function parseServerMessage(value: unknown): ServerMessage | null {
  if (!isRecord(value)) return null;
  const { t, seq, tick, d } = value;
  if (!isServerMessageType(t)) return null;
  if (!isIntAtLeast(seq, 0) || !isIntAtLeast(tick, 0) || !isRecord(d)) return null;
  if (!PAYLOAD_VALIDATORS[t](d)) return null;
  return { t, seq, tick, d } as ServerMessage;
}

/** Décode une trame WebSocket texte. Les trames binaires ou JSON invalides donnent null. */
export function decodeServerMessage(raw: unknown): ServerMessage | null {
  if (typeof raw !== 'string') return null;
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    return null;
  }
  return parseServerMessage(value);
}
