import { describe, expect, it } from 'vitest';
import { animKey, facingFromAim, hashString, SURVIVOR_VARIANTS, variantForId } from './survivors';

describe('survivants', () => {
  it('oriente selon l’angle (y vers le bas)', () => {
    expect(facingFromAim(0)).toBe('right');
    expect(facingFromAim(Math.PI / 2)).toBe('down');
    expect(facingFromAim(-Math.PI / 2)).toBe('up');
    expect(facingFromAim(Math.PI)).toBe('left');
    expect(facingFromAim(-Math.PI + 0.01)).toBe('left');
    expect(facingFromAim(2 * Math.PI + 0.1)).toBe('right');
  });

  it('choisit une variante stable par id, et toutes les variantes sont utilisées', () => {
    expect(variantForId('abc')).toBe(variantForId('abc'));
    const used = new Set(Array.from({ length: 64 }, (_, i) => variantForId(`joueur-${i}`)));
    expect(used.size).toBe(SURVIVOR_VARIANTS.length);
    expect(hashString('')).toBe(0x811c9dc5);
  });

  it('compose les clés d’animation', () => {
    expect(animKey('survivor_b', 'run', 'up')).toBe('survivor_b:run_up');
  });
});
