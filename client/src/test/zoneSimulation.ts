// Simulation déterministe client ↔ serveur pour les tests réseau : horloge virtuelle, latence et
// gigue sur un lien ordonné (comme TCP), serveur autoritaire minimal qui applique `step()`.
import type {
  ClientPayloads,
  EntityState,
  InputPayload,
  ServerMessage,
  ServerMessageType,
  WelcomePayload,
} from '../generated/protocol';
import type { CollisionGrid } from '../game/movement/CollisionGrid';
import { step, type MovementConfig, type Vec2 } from '../game/movement/step';
import type { ZoneLinkSocket } from '../net/ZoneClient';

type Handler = (message: ServerMessage) => void;

export interface SimulationOptions {
  readonly grid: CollisionGrid;
  readonly movement: MovementConfig & { readonly max_inputs_per_tick: number };
  readonly start: Vec2;
  readonly tickRate?: number;
  /** Latence aller (et retour), en ms. */
  readonly oneWayLatencyMs: number;
  /** Gigue maximale ajoutée à chaque message (le lien reste ordonné). */
  readonly jitterMs?: number;
  /** Trajectoire d'un second joueur, en fonction du temps serveur (ms). */
  readonly otherPlayer?: (t: number) => Vec2;
}

/** Générateur pseudo-aléatoire reproductible (mulberry32). */
function rng(seed: number): () => number {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export class ZoneSimulation implements ZoneLinkSocket {
  now = 0;
  readonly tickRate: number;
  /** Position autoritaire du joueur local côté serveur. */
  serverPos: Vec2;
  serverTick = 0;
  private seq = 0;
  private ackSeq = 0;
  private readonly inbox: { seq: number; input: InputPayload }[] = [];
  private readonly events: { at: number; order: number; run: () => void }[] = [];
  private order = 0;
  private lastToServer = 0;
  private lastToClient = 0;
  private readonly handlers = new Map<string, Set<Handler>>();
  private readonly random = rng(42);
  private welcomePayload: WelcomePayload | null = null;
  /** Décalage forcé appliqué par le serveur au prochain tick (pour simuler une divergence). */
  pendingServerNudge: Vec2 | null = null;

  constructor(private readonly opts: SimulationOptions) {
    this.tickRate = opts.tickRate ?? 20;
    this.serverPos = opts.start;
  }

  // --- ZoneLinkSocket ---
  on<K extends ServerMessageType>(
    type: K,
    handler: (message: Extract<ServerMessage, { t: K }>) => void,
  ): () => void {
    let set = this.handlers.get(type);
    if (!set) {
      set = new Set();
      this.handlers.set(type, set);
    }
    const h = handler as Handler;
    set.add(h);
    return () => set.delete(h);
  }

  sendWithSeq<K extends 'input' | 'action'>(t: K, payload: ClientPayloads[K]): number | null {
    // Seules les entrées de déplacement sont simulées ici.
    if (t !== 'input') return null;
    const d = payload as InputPayload;
    this.seq += 1;
    const seq = this.seq;
    this.lastToServer = this.schedule(this.lastToServer, () => this.inbox.push({ seq, input: d }));
    return seq;
  }

  getStatus(): { readonly welcome: WelcomePayload | null } {
    return { welcome: this.welcomePayload };
  }

  // --- Pilotage ---
  /** Envoie le welcome (après la latence) et démarre les ticks serveur. */
  start(): void {
    const welcome: WelcomePayload = {
      protocol_version: 2,
      zone_id: 'test',
      character_id: 'c1',
      tick_rate: this.tickRate,
      server_time: 0,
      entity_id: 'me',
      map_id: 'test',
    };
    this.lastToClient = this.schedule(this.lastToClient, () => {
      this.welcomePayload = welcome;
      this.emit({ t: 'welcome', seq: 1, tick: 0, d: welcome });
    });
    this.scheduleTick(1000 / this.tickRate);
  }

  /** Fait avancer l'horloge virtuelle jusqu'à `t` en exécutant les événements échus. */
  advanceTo(t: number): void {
    for (;;) {
      this.events.sort((a, b) => a.at - b.at || a.order - b.order);
      const next = this.events[0];
      if (!next || next.at > t) break;
      this.events.shift();
      this.now = next.at;
      next.run();
    }
    this.now = t;
  }

  private scheduleTick(at: number): void {
    this.push(at, () => {
      this.serverTick += 1;
      const n = Math.min(this.inbox.length, this.opts.movement.max_inputs_per_tick);
      for (const { seq, input } of this.inbox.splice(0, n)) {
        this.serverPos = step(this.serverPos, input, this.opts.grid, this.opts.movement, 1 / this.tickRate);
        this.ackSeq = seq;
      }
      if (this.pendingServerNudge) {
        this.serverPos = {
          x: this.serverPos.x + this.pendingServerNudge.x,
          y: this.serverPos.y + this.pendingServerNudge.y,
        };
        this.pendingServerNudge = null;
      }
      const tick = this.serverTick;
      const entities: EntityState[] = [
        {
          id: 'me',
          kind: 'player',
          name: 'Moi',
          x: this.serverPos.x,
          y: this.serverPos.y,
          aim: 0,
          anim: 'walk',
          health: 1,
        },
      ];
      const other = this.opts.otherPlayer?.(tick * (1000 / this.tickRate));
      if (other)
        entities.push({
          id: 'other',
          kind: 'player',
          name: 'Autre',
          ...other,
          aim: 0,
          anim: 'walk',
          health: 1,
        });
      const ack = this.ackSeq;
      this.lastToClient = this.schedule(this.lastToClient, () =>
        this.emit({ t: 'snapshot', seq: tick + 1, tick, d: { ack_seq: ack, entities } }),
      );
      this.scheduleTick(at + 1000 / this.tickRate);
    });
  }

  /** Programme une livraison sur un lien ordonné ; renvoie l'heure d'arrivée. */
  private schedule(lastArrival: number, run: () => void): number {
    const jitter = (this.opts.jitterMs ?? 0) * this.random();
    const at = Math.max(lastArrival, this.now + this.opts.oneWayLatencyMs + jitter);
    this.push(at, run);
    return at;
  }

  private push(at: number, run: () => void): void {
    this.order += 1;
    this.events.push({ at, order: this.order, run });
  }

  private emit(message: ServerMessage): void {
    this.handlers.get(message.t)?.forEach((h) => h(message));
  }
}
