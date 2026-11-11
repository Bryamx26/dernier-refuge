// Codes de fermeture WebSocket (docs/architecture/phase-1-contracts.md) et libellés d'interface.

export const CLOSE_CODES = {
  NORMAL: 1000,
  GOING_AWAY: 1001,
  ABNORMAL: 1006,
  INVALID_TICKET: 4001,
  ALREADY_CONNECTED: 4002,
  ZONE_FULL: 4003,
  UNKNOWN_ZONE: 4004,
  ABUSE: 4008,
} as const;

const LABELS: Record<number, string> = {
  [CLOSE_CODES.NORMAL]: 'Liaison fermée.',
  [CLOSE_CODES.GOING_AWAY]: 'Le serveur a coupé la liaison.',
  [CLOSE_CODES.ABNORMAL]: 'Liaison perdue.',
  [CLOSE_CODES.INVALID_TICKET]: "Ticket d'accès invalide ou expiré.",
  [CLOSE_CODES.ALREADY_CONNECTED]: 'Ce survivant est déjà connecté.',
  [CLOSE_CODES.ZONE_FULL]: 'Zone pleine.',
  [CLOSE_CODES.UNKNOWN_ZONE]: 'Zone inconnue.',
  [CLOSE_CODES.ABUSE]: 'Trop de messages refusés : liaison coupée.',
};

export function describeCloseCode(code: number | null): string {
  if (code === null) return '';
  return LABELS[code] ?? `Liaison fermée (code ${code}).`;
}
