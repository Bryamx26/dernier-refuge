import { describe, expect, it } from 'vitest';
import { CollisionGrid } from '../game/movement/CollisionGrid';
import { step } from '../game/movement/step';
import { LocalPredictor } from './prediction';

const cfg = { walk_speed: 3, sprint_speed: 5, player_half_size: 0.3 };
const grid = CollisionGrid.fromRows(['..........', '..........', '..........', '..........']);
const right = { move_x: 1, move_y: 0, sprint: false };

describe('LocalPredictor', () => {
  it('exige une position serveur avant de prédire', () => {
    const p = new LocalPredictor(grid, cfg, 0.05);
    expect(() => p.applyInput(1, right)).toThrow();
    p.reconcile(0, { x: 1.5, y: 1.5 });
    expect(p.applyInput(1, right).x).toBeCloseTo(1.65, 12);
  });

  it('rejoue les entrées non acquittées depuis la position serveur (erreur nulle si identique)', () => {
    const p = new LocalPredictor(grid, cfg, 0.05);
    p.reconcile(0, { x: 1.5, y: 1.5 });
    let server = { x: 1.5, y: 1.5 };
    for (let seq = 1; seq <= 5; seq += 1) p.applyInput(seq, right);
    // Le serveur a appliqué les entrées 1 à 3.
    for (let i = 0; i < 3; i += 1) server = step(server, right, grid, cfg, 0.05);
    const delta = p.reconcile(3, server);
    expect(Math.hypot(delta.x, delta.y)).toBeLessThan(1e-12);
    expect(p.pendingCount).toBe(2);
    expect(p.position!.x).toBeCloseTo(1.5 + 5 * 0.15, 12);
  });

  it('mesure la correction quand le serveur diverge', () => {
    const p = new LocalPredictor(grid, cfg, 0.05);
    p.reconcile(0, { x: 1.5, y: 1.5 });
    p.applyInput(2, right);
    p.applyInput(4, right);
    // Le serveur a appliqué l'entrée 2 mais place le joueur 0,4 tuile plus bas.
    const delta = p.reconcile(2, { x: 1.65, y: 1.9 });
    expect(delta.x).toBeCloseTo(0, 12);
    expect(delta.y).toBeCloseTo(0.4, 12);
    expect(p.position).toEqual({ x: expect.closeTo(1.8, 12) as number, y: 1.9 });
  });

  it('ignore un snapshot plus ancien que le dernier acquittement', () => {
    const p = new LocalPredictor(grid, cfg, 0.05);
    p.reconcile(5, { x: 2, y: 2 });
    const delta = p.reconcile(3, { x: 9, y: 9 });
    expect(delta).toEqual({ x: 0, y: 0 });
    expect(p.position).toEqual({ x: 2, y: 2 });
  });
});
