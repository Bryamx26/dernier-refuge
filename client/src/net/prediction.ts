// Prédiction locale et réconciliation sur `ack_seq` (logique pure, sans Phaser ni React).
// Chaque entrée envoyée est simulée tout de suite avec `step()` et gardée jusqu'à son acquittement.
// À chaque snapshot : on repart de la position serveur et on rejoue les entrées non acquittées ;
// l'écart entre la prédiction d'avant et celle d'après est l'erreur de réconciliation.
import type { CollisionGrid } from '../game/movement/CollisionGrid';
import { step, type MovementConfig, type MoveInput, type Vec2 } from '../game/movement/step';

export interface PendingInput {
  readonly seq: number;
  readonly input: MoveInput;
}

/** Au-delà, l'historique est tronqué (le serveur borne sa file à 64 entrées). */
export const MAX_PENDING_INPUTS = 128;

export class LocalPredictor {
  private pos: Vec2 | null = null;
  private readonly pending: PendingInput[] = [];
  private lastAck = 0;

  constructor(
    private readonly grid: CollisionGrid,
    private readonly cfg: MovementConfig,
    /** Durée d'un pas, en secondes (1 / tick_rate). */
    private readonly dt: number,
  ) {}

  get position(): Vec2 | null {
    return this.pos;
  }

  get pendingCount(): number {
    return this.pending.length;
  }

  get lastAckSeq(): number {
    return this.lastAck;
  }

  /** Simule une entrée envoyée sous le numéro `seq` ; renvoie la nouvelle position prédite. */
  applyInput(seq: number, input: MoveInput): Vec2 {
    if (!this.pos) throw new Error('Position locale inconnue : attendre le premier snapshot');
    this.pos = step(this.pos, input, this.grid, this.cfg, this.dt);
    this.pending.push({ seq, input });
    if (this.pending.length > MAX_PENDING_INPUTS)
      this.pending.splice(0, this.pending.length - MAX_PENDING_INPUTS);
    return this.pos;
  }

  /**
   * Applique l'état serveur : position après l'entrée `ackSeq`. Renvoie le déplacement de correction
   * (position réconciliée − position prédite avant), nul si la prédiction était juste.
   */
  reconcile(ackSeq: number, server: Vec2): Vec2 {
    // Un snapshot plus ancien que le dernier acquittement (réordonnancement) est ignoré.
    if (ackSeq < this.lastAck) return { x: 0, y: 0 };
    this.lastAck = ackSeq;
    let drop = 0;
    while (drop < this.pending.length && this.pending[drop]!.seq <= ackSeq) drop += 1;
    this.pending.splice(0, drop);

    let replayed: Vec2 = { x: server.x, y: server.y };
    for (const { input } of this.pending) replayed = step(replayed, input, this.grid, this.cfg, this.dt);

    const before = this.pos;
    this.pos = replayed;
    if (!before) return { x: 0, y: 0 };
    return { x: replayed.x - before.x, y: replayed.y - before.y };
  }
}
