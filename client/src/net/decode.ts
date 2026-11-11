// Décodage et validation des messages serveur. Tout message invalide ou de type inconnu est rejeté (null).
import {
  SERVER_MESSAGE_TYPES,
  type ErrorCode,
  type ServerMessage,
  type ServerMessageType,
  type ServerPayloads,
} from '../generated/protocol';

type UnknownRecord = Record<string, unknown>;

const ERROR_CODES: readonly ErrorCode[] = ['bad_message', 'unknown_type', 'rate_limited', 'internal'];

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
    isNonNegative(d.server_time),
  pong: (d): d is UnknownRecord & ServerPayloads['pong'] =>
    isNonNegative(d.client_time) && isNonNegative(d.server_time),
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
