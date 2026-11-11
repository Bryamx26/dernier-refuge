// Interpolation des entités distantes : on affiche le monde avec un retard fixe (100 ms) pour
// toujours disposer de deux snapshots encadrants. Logique pure, horloges injectées en millisecondes.
import type { AnimState, EntityState } from '../generated/protocol';

export const INTERPOLATION_DELAY_MS = 100;
/** Historique conservé par entité. */
const BUFFER_SPAN_MS = 1000;
/** Vitesse de remontée de l'estimation du décalage d'horloge (la baisse est immédiate). */
const OFFSET_DRIFT = 0.02;

interface Sample {
  /** Temps serveur du snapshot (tick × durée d'un tick), en ms. */
  readonly t: number;
  readonly x: number;
  readonly y: number;
  readonly aim: number;
  readonly anim: AnimState;
  readonly name: string;
}

export interface RemoteEntityView {
  readonly id: string;
  readonly name: string;
  readonly x: number;
  readonly y: number;
  readonly aim: number;
  readonly anim: AnimState;
}

/** Interpolation d'angle par le plus court chemin. */
export function lerpAngle(a: number, b: number, t: number): number {
  let d = (b - a) % (2 * Math.PI);
  if (d > Math.PI) d -= 2 * Math.PI;
  if (d < -Math.PI) d += 2 * Math.PI;
  return a + d * t;
}

export class InterpolationBuffer {
  private readonly buffers = new Map<string, Sample[]>();
  /** Estimation de (temps local de réception − temps serveur) ; null avant le premier snapshot. */
  private offset: number | null = null;

  constructor(
    private readonly tickMs: number,
    private readonly delayMs = INTERPOLATION_DELAY_MS,
  ) {}

  /** Nombre d'entités suivies. */
  get size(): number {
    return this.buffers.size;
  }

  /**
   * Enregistre un snapshot reçu à `receivedAt` (horloge locale). `excludeId` (le joueur local,
   * prédit à part) n'est pas suivi. Les entités absentes du snapshot disparaissent.
   */
  push(tick: number, entities: readonly EntityState[], receivedAt: number, excludeId?: string): void {
    const t = tick * this.tickMs;
    // Décalage d'horloge : on suit le transit le plus court (les paquets en retard ne décalent pas
    // l'affichage), avec une lente remontée pour suivre une dérive.
    const sample = receivedAt - t;
    if (this.offset === null || sample < this.offset) this.offset = sample;
    else this.offset += (sample - this.offset) * OFFSET_DRIFT;

    const seen = new Set<string>();
    for (const e of entities) {
      if (e.id === excludeId) continue;
      seen.add(e.id);
      let buffer = this.buffers.get(e.id);
      if (!buffer) {
        buffer = [];
        this.buffers.set(e.id, buffer);
      }
      const last = buffer[buffer.length - 1];
      // Snapshot dupliqué ou réordonné : ignoré.
      if (last && t <= last.t) continue;
      buffer.push({ t, x: e.x, y: e.y, aim: e.aim, anim: e.anim, name: e.name });
      while (buffer.length > 2 && buffer[0]!.t < t - BUFFER_SPAN_MS) buffer.shift();
    }
    for (const id of [...this.buffers.keys()]) if (!seen.has(id)) this.buffers.delete(id);
  }

  /** Temps serveur affiché à l'instant local `now`. */
  renderTime(now: number): number | null {
    return this.offset === null ? null : now - this.offset - this.delayMs;
  }

  /** États interpolés de toutes les entités distantes à l'instant local `now`. */
  sample(now: number): RemoteEntityView[] {
    const rt = this.renderTime(now);
    if (rt === null) return [];
    const views: RemoteEntityView[] = [];
    for (const [id, buffer] of this.buffers) {
      const view = sampleBuffer(id, buffer, rt);
      if (view) views.push(view);
    }
    return views;
  }

  clear(): void {
    this.buffers.clear();
    this.offset = null;
  }
}

function sampleBuffer(id: string, buffer: readonly Sample[], rt: number): RemoteEntityView | null {
  const first = buffer[0];
  const last = buffer[buffer.length - 1];
  if (!first || !last) return null;
  // Hors de l'intervalle connu : on tient la position extrême (pas d'extrapolation).
  if (rt <= first.t) return toView(id, first);
  if (rt >= last.t) return toView(id, last);
  let i = buffer.length - 2;
  while (i > 0 && buffer[i]!.t > rt) i -= 1;
  const a = buffer[i]!;
  const b = buffer[i + 1]!;
  const k = (rt - a.t) / (b.t - a.t);
  return {
    id,
    name: b.name,
    x: a.x + (b.x - a.x) * k,
    y: a.y + (b.y - a.y) * k,
    aim: lerpAngle(a.aim, b.aim, k),
    anim: k < 0.5 ? a.anim : b.anim,
  };
}

function toView(id: string, s: Sample): RemoteEntityView {
  return { id, name: s.name, x: s.x, y: s.y, aim: s.aim, anim: s.anim };
}
