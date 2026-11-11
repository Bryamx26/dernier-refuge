import { describe, expect, it } from 'vitest';
import type { EntityState } from '../generated/protocol';
import { InterpolationBuffer, lerpAngle } from './interpolation';

function entity(id: string, x: number, y = 0, aim = 0): EntityState {
  return { id, kind: 'player', name: id.toUpperCase(), x, y, aim, anim: 'walk', health: 1 };
}

describe('InterpolationBuffer', () => {
  it('affiche les entités 100 ms dans le passé, interpolées linéairement', () => {
    const buffer = new InterpolationBuffer(50);
    // Tick n reçu à 1000 + 50 n ms (transit constant).
    for (let tick = 0; tick <= 4; tick += 1) buffer.push(tick, [entity('a', tick)], 1000 + tick * 50);
    // À 1175 ms : temps serveur affiché = 1175 − 1000 − 100 = 75 ms, soit le tick 1,5.
    const [a] = buffer.sample(1175);
    expect(a?.x).toBeCloseTo(1.5, 12);
    expect(a?.name).toBe('A');
  });

  it('exclut le joueur local et retire les entités absentes du snapshot', () => {
    const buffer = new InterpolationBuffer(50);
    buffer.push(1, [entity('me', 0), entity('a', 0), entity('b', 0)], 100, 'me');
    expect(buffer.size).toBe(2);
    buffer.push(2, [entity('me', 0), entity('a', 1)], 150, 'me');
    expect(buffer.sample(300).map((e) => e.id)).toEqual(['a']);
  });

  it('tient la dernière position sans extrapoler et résiste à la gigue', () => {
    const buffer = new InterpolationBuffer(50);
    buffer.push(0, [entity('a', 0)], 0);
    buffer.push(1, [entity('a', 1)], 90); // en retard de 40 ms : n'avance pas l'horloge d'affichage
    buffer.push(2, [entity('a', 2)], 100);
    expect(buffer.renderTime(200)).toBeCloseTo(100, 6);
    expect(buffer.sample(500)[0]?.x).toBe(2);
  });

  it('interpole les angles par le plus court chemin', () => {
    expect(lerpAngle(3, -3, 0.5)).toBeCloseTo(Math.PI, 1);
    expect(lerpAngle(0.1, 0.3, 0.5)).toBeCloseTo(0.2, 12);
  });
});
