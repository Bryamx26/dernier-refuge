import { describe, expect, it } from 'vitest';
import { CollisionGrid } from '../game/movement/CollisionGrid';
import { ZoneSimulation } from '../test/zoneSimulation';
import { ZoneClient, type InputIntent } from './ZoneClient';

const movement = { walk_speed: 3, sprint_speed: 5, player_half_size: 0.3, max_inputs_per_tick: 3 };

// Arène 24 × 16 entourée de murs, avec un bloc au milieu pour provoquer des glissements.
const rows = Array.from({ length: 16 }, (_, y) =>
  Array.from({ length: 24 }, (_, x) =>
    x === 0 || y === 0 || x === 23 || y === 15 || (x >= 10 && x <= 12 && y >= 6 && y <= 8) ? '#' : '.',
  ).join(''),
);
const grid = CollisionGrid.fromRows(rows);

/** Parcours « marche normale » : marche, diagonales contre le bloc, sprint, arrêts, mur extérieur. */
function intentAt(t: number): InputIntent {
  const phases: [number, number, number, boolean][] = [
    [1500, 1, 0, false],
    [2500, 1, 1, false],
    [3500, 0, -1, true],
    [4000, 0, 0, false],
    [5500, -1, 0.5, false],
    [6500, 1, 0, true],
    [7000, 0, 0, false],
    [9000, 0, 1, false], // jusqu'au mur du bas
    [10000, -1, -1, true],
  ];
  for (const [end, mx, my, sprint] of phases) if (t < end) return { move_x: mx, move_y: my, sprint, aim: 0 };
  return { move_x: 0, move_y: 0, sprint: false, aim: 0 };
}

function run(sim: ZoneSimulation, client: ZoneClient, durationMs: number, frameMs = 1000 / 60) {
  let maxCorrection = 0;
  let maxFrameJump = 0;
  let previous: { x: number; y: number } | null = null;
  for (let t = 0; t <= durationMs; t += frameMs) {
    sim.advanceTo(t);
    client.update(t, intentAt(t));
    maxCorrection = Math.max(maxCorrection, client.getStats(t).correctionTiles);
    const local = client.getLocalPlayer();
    if (local && previous)
      maxFrameJump = Math.max(maxFrameJump, Math.hypot(local.x - previous.x, local.y - previous.y));
    if (local) previous = { x: local.x, y: local.y };
  }
  return { maxCorrection, maxFrameJump };
}

describe('ZoneClient', () => {
  it('à 150 ms de latence (aller et retour, avec gigue), la correction reste < 0,25 tuile en marche normale', () => {
    const sim = new ZoneSimulation({
      grid,
      movement,
      start: { x: 4.5, y: 4.5 },
      oneWayLatencyMs: 150,
      jitterMs: 30,
      otherPlayer: (t) => ({ x: 15 + Math.sin(t / 1000) * 3, y: 11 }),
    });
    const client = new ZoneClient(sim, { movement, now: () => sim.now });
    client.setCollisionGrid(grid);
    sim.start();
    const { maxCorrection, maxFrameJump } = run(sim, client, 11000);

    expect(client.ready).toBe(true);
    // Le parcours a bien déplacé le joueur (et l'a collé aux murs).
    expect(Math.hypot(sim.serverPos.x - 4.5, sim.serverPos.y - 4.5)).toBeGreaterThan(2);
    expect(maxCorrection).toBeLessThan(0.25);
    // Fluidité : jamais plus d'un pas de sprint (5 t/s × 50 ms) entre deux images.
    expect(maxFrameJump).toBeLessThanOrEqual(0.25 + 1e-9);
    // Une fois tout acquitté, prédiction et serveur coïncident.
    sim.advanceTo(12000);
    client.update(12000, { move_x: 0, move_y: 0, sprint: false, aim: 0 });
    const stats = client.getStats(12000);
    expect(stats.position!.x).toBeCloseTo(sim.serverPos.x, 9);
    expect(stats.position!.y).toBeCloseTo(sim.serverPos.y, 9);
    expect(stats.visiblePlayers).toBe(2);
  });

  it('envoie un input par pas fixe de 1/tick_rate, avec des seq croissants', () => {
    const sim = new ZoneSimulation({ grid, movement, start: { x: 4.5, y: 4.5 }, oneWayLatencyMs: 20 });
    const sent: number[] = [];
    const original = sim.sendWithSeq.bind(sim);
    sim.sendWithSeq = (t, d) => {
      const seq = original(t, d);
      if (seq !== null) sent.push(seq);
      return seq;
    };
    const client = new ZoneClient(sim, { movement, now: () => sim.now });
    client.setCollisionGrid(grid);
    sim.start();
    // Prêt après welcome + premier snapshot (~70 ms) ; puis 2 s à 60 i/s.
    run(sim, client, 200);
    const before = sent.length;
    for (let t = 200; t <= 2200; t += 1000 / 60) {
      sim.advanceTo(t);
      client.update(t, intentAt(0));
    }
    expect(sent.length - before).toBeGreaterThanOrEqual(39);
    expect(sent.length - before).toBeLessThanOrEqual(41);
  });

  it('mesure et lisse une correction quand le serveur diverge', () => {
    const sim = new ZoneSimulation({ grid, movement, start: { x: 4.5, y: 4.5 }, oneWayLatencyMs: 75 });
    const client = new ZoneClient(sim, { movement, now: () => sim.now });
    client.setCollisionGrid(grid);
    sim.start();
    run(sim, client, 1000);
    sim.pendingServerNudge = { x: 0, y: 0.5 };
    let t = 1000;
    let before = client.getLocalPlayer()!;
    let maxJump = 0;
    for (; t < 1600; t += 1000 / 60) {
      sim.advanceTo(t);
      client.update(t, intentAt(0));
      const now = client.getLocalPlayer()!;
      maxJump = Math.max(maxJump, Math.abs(now.y - before.y));
      before = now;
    }
    expect(client.getStats(t).lastCorrectionTiles).toBeCloseTo(0.5, 6);
    // Le sprite glisse vers la position corrigée au lieu de sauter de 0,5 tuile.
    expect(maxJump).toBeLessThan(0.2);
  });

  it('interpole l’autre joueur à environ 100 ms + latence dans le passé', () => {
    const path = (t: number) => ({ x: 5 + t / 1000, y: 10 });
    const sim = new ZoneSimulation({
      grid,
      movement,
      start: { x: 4.5, y: 4.5 },
      oneWayLatencyMs: 50,
      otherPlayer: path,
    });
    const client = new ZoneClient(sim, { movement, now: () => sim.now });
    client.setCollisionGrid(grid);
    sim.start();
    run(sim, client, 2000);
    const [other] = client.getRemotePlayers(2000);
    expect(other?.id).toBe('other');
    // Temps serveur affiché ≈ 2000 − 50 (transit) − 100 (retard) = 1850 ms.
    expect(other!.x).toBeCloseTo(path(1850).x, 1);
  });
});
