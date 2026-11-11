// Palette partagée par l'interface (via les variables CSS de theme.css) et par Phaser.
// Garder ces valeurs synchronisées avec le bloc @theme de theme.css.

export const palette = {
  charcoal950: '#0b0d0c',
  charcoal900: '#121514',
  charcoal800: '#1a1e1c',
  charcoal700: '#262b28',
  charcoal600: '#353b37',
  ash: '#8a8f86',
  bone: '#c8c5b4',
  verdigris300: '#9fbfae',
  verdigris400: '#7fa392',
  verdigris500: '#5f8a76',
  verdigris700: '#36564a',
  rust400: '#c26a45',
  rust500: '#a64b2a',
  amber: '#c9a14a',
} as const;

export const fonts = {
  /** Titres et libellés. */
  display: '"Silkscreen", "VT323", monospace',
  /** Texte de terminal. */
  terminal: '"VT323", monospace',
} as const;

/** Convertit `#rrggbb` en entier 0xRRGGBB (couleurs Phaser). */
export function hexToNumber(hex: string): number {
  return Number.parseInt(hex.replace('#', ''), 16);
}
