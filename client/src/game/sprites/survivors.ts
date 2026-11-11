// Sprites de survivants (assets/sprites/survivor*.png + .json, Kenney RPG Urban Pack, CC0).
// Logique pure : choix de variante, orientation, clés d'animation. Aucune dépendance à Phaser.
import type { AnimState } from '../../generated/protocol';

export type Facing = 'down' | 'left' | 'right' | 'up';

/** Variantes disponibles ; l'apparence d'un joueur est fixée par son id (identique chez tous les clients). */
export const SURVIVOR_VARIANTS = ['survivor', 'survivor_b', 'survivor_c', 'survivor_d'] as const;
export type SurvivorVariant = (typeof SURVIVOR_VARIANTS)[number];

/** Sprite de secours si un asset manque : texture générée, clairement nommée. */
export const PLACEHOLDER_SPRITE = 'survivor_PLACEHOLDER';

export const GAME_DATA_URL = '/game';
export const spriteUrls = (variant: string) => ({
  json: `${GAME_DATA_URL}/assets/sprites/${variant}.json`,
  png: `${GAME_DATA_URL}/assets/sprites/${variant}.png`,
});

/** Description d'une planche (`survivor.json`). */
export interface SurvivorSheet {
  readonly frameWidth: number;
  readonly frameHeight: number;
  readonly directions: readonly Facing[];
  readonly animations: Readonly<
    Record<string, { readonly frames: readonly number[]; readonly fps: number; readonly loop: boolean }>
  >;
  readonly anchor?: { readonly x: number; readonly y: number };
}

export function isSurvivorSheet(value: unknown): value is SurvivorSheet {
  if (typeof value !== 'object' || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.frameWidth === 'number' &&
    typeof v.frameHeight === 'number' &&
    Array.isArray(v.directions) &&
    typeof v.animations === 'object' &&
    v.animations !== null
  );
}

/** Hachage FNV-1a 32 bits (stable entre navigateurs). */
export function hashString(text: string): number {
  let hash = 0x811c9dc5;
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

export function variantForId(id: string, variants: readonly string[] = SURVIVOR_VARIANTS): string {
  if (variants.length === 0) return PLACEHOLDER_SPRITE;
  return variants[hashString(id) % variants.length]!;
}

/** Orientation à 4 directions depuis un angle (0 = droite, sens horaire écran, y vers le bas). */
export function facingFromAim(aim: number): Facing {
  if (!Number.isFinite(aim)) return 'down';
  const a = Math.atan2(Math.sin(aim), Math.cos(aim));
  const q = Math.PI / 4;
  if (a > -q && a <= q) return 'right';
  if (a > q && a <= 3 * q) return 'down';
  if (a > -3 * q && a <= -q) return 'up';
  return 'left';
}

/** Clé d'animation Phaser : `<variante>:<état>_<direction>` (états de survivor.json). */
export function animKey(variant: string, anim: AnimState, facing: Facing): string {
  return `${variant}:${anim}_${facing}`;
}
