// Port TypeScript exact de `step()` — référence : server/app/zone/movement.py, verrouillée par
// shared/fixtures/movement.json. Mêmes opérations IEEE 754, dans le même ordre, mêmes comparaisons
// (pas de Math.hypot ni de min/max sur des flottants) : résultats identiques au bit près.
//
// Unités : tuiles et secondes. x vers la droite, y vers le bas ; la tuile (tx, ty) couvre
// [tx, tx + 1[ × [ty, ty + 1[. La position est le centre de la boîte AABB de demi-côté `h`.
import type { CollisionGrid } from './CollisionGrid';

export interface Vec2 {
  readonly x: number;
  readonly y: number;
}

/** Entrée de déplacement d'un pas (mêmes champs que le message `input`, `aim` excepté). */
export interface MoveInput {
  readonly move_x: number;
  readonly move_y: number;
  readonly sprint: boolean;
}

export interface MovementConfig {
  readonly walk_speed: number;
  readonly sprint_speed: number;
  readonly player_half_size: number;
}

/**
 * Tolérance des tests de recouvrement : une boîte à moins de EPSILON d'une frontière de tuile est
 * « au contact », pas « dedans » (le recalage exact contre un mur peut dépasser l'entier de quelques ulps).
 */
export const EPSILON = 1e-9;

/** Borne un axe à [-1, 1] ; une valeur non finie (NaN, ±inf) vaut 0. */
function clampAxis(value: number): number {
  if (!Number.isFinite(value)) return 0;
  if (value > 1) return 1;
  if (value < -1) return -1;
  return value;
}

/**
 * Étape 1 : axes bornés, puis normalisés si `norme² > 1` (comparaison stricte), avec
 * `sqrt(mx*mx + my*my)` et une division axe par axe.
 */
export function normalizeMove(moveX: number, moveY: number): Vec2 {
  let mx = clampAxis(moveX);
  let my = clampAxis(moveY);
  const squared = mx * mx + my * my;
  if (squared > 1) {
    const norm = Math.sqrt(squared);
    mx = mx / norm;
    my = my / norm;
  }
  return { x: mx, y: my };
}

/** Première tuile recouverte par une boîte de bord bas `lowEdge` : floor(lowEdge + ε). */
export function firstTile(lowEdge: number): number {
  return Math.floor(lowEdge + EPSILON);
}

/** Dernière tuile recouverte par une boîte de bord haut `highEdge` : floor(highEdge − ε). */
export function lastTile(highEdge: number): number {
  return Math.floor(highEdge - EPSILON);
}

/** Vrai si la boîte centrée en (x, y) recouvre une tuile solide (ou hors carte). */
export function overlapsSolid(x: number, y: number, grid: CollisionGrid, half: number): boolean {
  return grid.anySolid(firstTile(x - half), lastTile(x + half), firstTile(y - half), lastTile(y + half));
}

/**
 * Déplace `center` de `delta` sur un axe, contre les tuiles solides. `solidAt(i)` : la colonne
 * (ou ligne) `i` contient une tuile solide parmi celles recouvertes sur l'autre axe.
 */
function moveAxis(center: number, delta: number, half: number, solidAt: (index: number) => boolean): number {
  const target = center + delta;
  if (delta > 0) {
    // Balayage des tuiles franchies par le bord haut, de la plus proche à la plus lointaine.
    // Les tuiles déjà recouvertes au départ sont ignorées (on peut sortir d'un mur).
    const start = lastTile(center + half) + 1;
    const end = lastTile(target + half);
    for (let index = start; index <= end; index += 1) {
      if (solidAt(index)) return index - half;
    }
    return target;
  }
  if (delta < 0) {
    const start = firstTile(center - half) - 1;
    const end = firstTile(target - half);
    for (let index = start; index >= end; index -= 1) {
      if (solidAt(index)) return index + 1 + half;
    }
    return target;
  }
  return center;
}

/**
 * Un pas de simulation de durée `dt` secondes (fonction pure) : axe X à y inchangé, puis axe Y avec
 * le nouveau x. Le balayage tuile par tuile empêche de traverser un mur quel que soit `dt`.
 */
export function step(
  pos: Vec2,
  input: MoveInput,
  grid: CollisionGrid,
  cfg: MovementConfig,
  dt: number,
): Vec2 {
  const half = cfg.player_half_size;
  const move = normalizeMove(input.move_x, input.move_y);
  const speed = input.sprint ? cfg.sprint_speed : cfg.walk_speed;
  // Multiplications de gauche à droite, comme en Python.
  const dx = move.x * speed * dt;
  const dy = move.y * speed * dt;

  const ty0 = firstTile(pos.y - half);
  const ty1 = lastTile(pos.y + half);
  const x = moveAxis(pos.x, dx, half, (tx) => grid.anySolid(tx, tx, ty0, ty1));

  const tx0 = firstTile(x - half);
  const tx1 = lastTile(x + half);
  const y = moveAxis(pos.y, dy, half, (ty) => grid.anySolid(tx0, tx1, ty, ty));
  return { x, y };
}
