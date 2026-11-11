// Formatage des valeurs du HUD (virgule décimale française).

/** Au-delà, la correction est jugée visible à l'écran (critère de la phase 2 : < 0,25 tuile). */
export const CORRECTION_WARN_TILES = 0.25;

export function formatTiles(value: number | null): string {
  return value === null ? '—' : value.toFixed(1).replace('.', ',');
}

export function formatCorrection(value: number): string {
  return `${value.toFixed(2).replace('.', ',')} t`;
}
