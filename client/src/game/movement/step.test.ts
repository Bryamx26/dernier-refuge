// Exécute TOUS les cas de shared/fixtures/movement.json (générés par le serveur, référence Python).
import { describe, expect, it } from 'vitest';
import { CollisionGrid } from './CollisionGrid';
import { MOVEMENT } from './config';
import { normalizeMove, step, type MoveInput, type Vec2 } from './step';

interface MovementFixture {
  readonly name: string;
  readonly description?: string;
  readonly grid: readonly string[];
  readonly start: Vec2;
  readonly dt: number;
  readonly inputs: readonly MoveInput[];
  readonly expected: readonly Vec2[];
}

const TOLERANCE = 1e-9;

// import.meta.glob : un fichier absent donne un objet vide (le test échoue alors explicitement).
const modules = import.meta.glob<readonly MovementFixture[]>('@shared/fixtures/movement.json', {
  eager: true,
  import: 'default',
});
const fixtures = Object.values(modules)[0] ?? [];

describe('step() — fixtures partagées', () => {
  it('trouve les fixtures du serveur', () => {
    expect(fixtures.length).toBeGreaterThan(0);
  });

  it.each(fixtures.map((f) => [f.name, f] as const))('%s', (_name, fixture) => {
    const grid = CollisionGrid.fromRows(fixture.grid);
    expect(fixture.expected).toHaveLength(fixture.inputs.length);
    let pos: Vec2 = fixture.start;
    fixture.inputs.forEach((input, i) => {
      pos = step(pos, input, grid, MOVEMENT, fixture.dt);
      const expected = fixture.expected[i]!;
      expect(Math.abs(pos.x - expected.x), `${fixture.name} pas ${i} x`).toBeLessThanOrEqual(TOLERANCE);
      expect(Math.abs(pos.y - expected.y), `${fixture.name} pas ${i} y`).toBeLessThanOrEqual(TOLERANCE);
    });
  });
});

describe('step() — propriétés', () => {
  const open = CollisionGrid.fromRows(['.....', '.....', '.....']);

  it('normalise une diagonale et laisse une norme ≤ 1 intacte', () => {
    const d = normalizeMove(1, 1);
    expect(d.x).toBeCloseTo(Math.SQRT1_2, 15);
    expect(normalizeMove(0.5, -0.5)).toEqual({ x: 0.5, y: -0.5 });
    expect(normalizeMove(Number.NaN, 3)).toEqual({ x: 0, y: 1 });
  });

  it('considère le hors-carte comme solide', () => {
    const pos = step({ x: 0.5, y: 1.5 }, { move_x: -1, move_y: 0, sprint: true }, open, MOVEMENT, 1);
    expect(pos.x).toBe(0.3);
  });
});

describe('CollisionGrid.fromTiledMap', () => {
  it('rend solide toute tuile non nulle du calque collision (même dans un groupe)', () => {
    const grid = CollisionGrid.fromTiledMap({
      width: 3,
      height: 2,
      layers: [
        { name: 'ground', type: 'tilelayer', data: [1, 1, 1, 1, 1, 1] },
        {
          name: 'g',
          type: 'group',
          layers: [{ name: 'collision', type: 'tilelayer', data: [0, 5, 0, 0, 0, 7] }],
        },
      ],
    });
    expect([grid.isSolid(0, 0), grid.isSolid(1, 0), grid.isSolid(2, 1), grid.isSolid(3, 0)]).toEqual([
      false,
      true,
      true,
      true,
    ]);
  });

  it('échoue si le calque est absent', () => {
    expect(() => CollisionGrid.fromTiledMap({ width: 1, height: 1, layers: [] })).toThrow(/collision/);
  });
});
