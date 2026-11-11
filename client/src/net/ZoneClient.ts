// Client de zone « jeu » : au-dessus du ZoneSocket, envoie un `input` par pas fixe, prédit le joueur
// local, réconcilie sur `ack_seq` et interpole les autres joueurs. Logique pure, pilotée par
// `update(now, intent)` à chaque image (Phaser) ou par un test avec une horloge simulée.
import type { InputPayload, ServerMessage, ServerMessageType, WelcomePayload } from '../generated/protocol';
import type { CollisionGrid } from '../game/movement/CollisionGrid';
import { MOVEMENT } from '../game/movement/config';
import type { MovementConfig, Vec2 } from '../game/movement/step';
import { InterpolationBuffer, type RemoteEntityView } from './interpolation';
import { LocalPredictor } from './prediction';

/** Ce que le ZoneClient utilise du ZoneSocket (remplaçable par un faux dans les tests). */
export interface ZoneLinkSocket {
  on<K extends ServerMessageType>(
    type: K,
    handler: (message: Extract<ServerMessage, { t: K }>) => void,
  ): () => void;
  sendWithSeq(t: 'input', d: InputPayload): number | null;
  getStatus(): { readonly welcome: WelcomePayload | null };
}

/** Intention du joueur à l'instant présent (clavier + souris). */
export type InputIntent = InputPayload;

export const IDLE_INTENT: InputIntent = { move_x: 0, move_y: 0, aim: 0, sprint: false };

export interface LocalPlayerView {
  readonly id: string;
  readonly x: number;
  readonly y: number;
  readonly aim: number;
  readonly anim: 'idle' | 'walk' | 'run';
}

export interface ZoneClientStats {
  /** Position prédite du joueur, en tuiles. */
  readonly position: Vec2 | null;
  /** Joueurs visibles dans le dernier snapshot (joueur local compris). */
  readonly visiblePlayers: number;
  /** Plus forte correction de réconciliation sur la fenêtre récente, en tuiles. */
  readonly correctionTiles: number;
  /** Dernière correction non nulle, en tuiles. */
  readonly lastCorrectionTiles: number;
  /** Entrées envoyées et pas encore acquittées. */
  readonly pendingInputs: number;
}

export interface ZoneClientOptions {
  /** Constantes de déplacement ; shared/movement/movement.json par défaut. */
  readonly movement?: MovementConfig;
  /** Horloge locale en millisecondes (performance.now() par défaut). */
  readonly now?: () => number;
  /** Retard d'interpolation des entités distantes. */
  readonly interpolationDelayMs?: number;
}

/** Au plus ce nombre de pas rattrapés en une image (onglet en arrière-plan, gel). */
const MAX_CATCH_UP_STEPS = 5;
/** Constante de temps du lissage visuel d'une correction, en ms. */
const CORRECTION_SMOOTHING_MS = 100;
/** Au-delà de cet écart (tuiles), la correction est appliquée d'un coup (téléportation). */
const SNAP_DISTANCE = 2;
/** Fenêtre de la mesure « correction récente » affichée au HUD. */
const CORRECTION_WINDOW_MS = 3000;

export class ZoneClient {
  private welcomePayload: WelcomePayload | null;
  private grid: CollisionGrid | null = null;
  private predictor: LocalPredictor | null = null;
  private interpolation: InterpolationBuffer | null = null;
  /** Dernier état serveur du joueur local reçu avant que la prédiction soit prête. */
  private pendingServerState: { ack: number; pos: Vec2 } | null = null;
  private accumulatorMs = 0;
  private lastUpdate: number | null = null;
  private previousPos: Vec2 | null = null;
  private visualOffset: Vec2 = { x: 0, y: 0 };
  private intent: InputIntent = IDLE_INTENT;
  private visible = 0;
  private corrections: { t: number; d: number }[] = [];
  private lastCorrection = 0;
  private readonly unsubscribe: (() => void)[] = [];
  private readonly now: () => number;

  constructor(
    private readonly socket: ZoneLinkSocket,
    private readonly options: ZoneClientOptions = {},
  ) {
    this.now = options.now ?? (() => performance.now());
    this.welcomePayload = socket.getStatus().welcome;
    this.unsubscribe.push(
      socket.on('welcome', (m) => this.handleWelcome(m.d)),
      socket.on('snapshot', (m) => this.handleSnapshot(m.tick, m.d.ack_seq, m.d.entities)),
    );
    if (this.welcomePayload) this.handleWelcome(this.welcomePayload);
  }

  get welcome(): WelcomePayload | null {
    return this.welcomePayload;
  }

  /** Durée d'un pas de simulation (1 / tick_rate), en ms. */
  get stepMs(): number {
    return 1000 / (this.welcomePayload?.tick_rate ?? 20);
  }

  /** Vrai dès que la carte et la position du joueur sont connues : la prédiction tourne. */
  get ready(): boolean {
    return this.predictor?.position != null;
  }

  /** À appeler une fois la carte chargée (calque `collision`). */
  setCollisionGrid(grid: CollisionGrid): void {
    this.grid = grid;
    this.ensurePredictor();
  }

  /**
   * Avance l'horloge locale : envoie un `input` par pas fixe écoulé (avec l'intention courante)
   * et le simule aussitôt. À appeler à chaque image.
   */
  update(now: number, intent: InputIntent): void {
    this.intent = intent;
    const elapsed = this.lastUpdate === null ? 0 : Math.max(0, now - this.lastUpdate);
    this.lastUpdate = now;
    this.decayVisualOffset(elapsed);
    const predictor = this.predictor;
    if (!predictor?.position) {
      this.accumulatorMs = 0;
      return;
    }
    const stepMs = this.stepMs;
    this.accumulatorMs = Math.min(this.accumulatorMs + elapsed, stepMs * MAX_CATCH_UP_STEPS);
    while (this.accumulatorMs >= stepMs) {
      this.accumulatorMs -= stepMs;
      const seq = this.socket.sendWithSeq('input', intent);
      if (seq === null) {
        this.accumulatorMs = 0;
        break;
      }
      this.previousPos = predictor.position;
      predictor.applyInput(seq, intent);
    }
  }

  /** Joueur local à afficher : interpolé entre les deux derniers pas, plus la correction lissée. */
  getLocalPlayer(): LocalPlayerView | null {
    const pos = this.predictor?.position;
    const id = this.welcomePayload?.entity_id;
    if (!pos || !id) return null;
    const prev = this.previousPos ?? pos;
    const alpha = Math.min(1, this.accumulatorMs / this.stepMs);
    const moving = this.intent.move_x !== 0 || this.intent.move_y !== 0;
    return {
      id,
      x: prev.x + (pos.x - prev.x) * alpha + this.visualOffset.x,
      y: prev.y + (pos.y - prev.y) * alpha + this.visualOffset.y,
      aim: this.intent.aim,
      anim: moving ? (this.intent.sprint ? 'run' : 'walk') : 'idle',
    };
  }

  /** Autres joueurs, interpolés avec retard. */
  getRemotePlayers(now: number = this.now()): RemoteEntityView[] {
    return this.interpolation?.sample(now) ?? [];
  }

  getStats(now: number = this.now()): ZoneClientStats {
    this.pruneCorrections(now);
    return {
      position: this.predictor?.position ?? this.pendingServerState?.pos ?? null,
      visiblePlayers: this.visible,
      correctionTiles: this.corrections.reduce((max, c) => Math.max(max, c.d), 0),
      lastCorrectionTiles: this.lastCorrection,
      pendingInputs: this.predictor?.pendingCount ?? 0,
    };
  }

  dispose(): void {
    this.unsubscribe.forEach((off) => off());
    this.unsubscribe.length = 0;
  }

  private handleWelcome(welcome: WelcomePayload): void {
    this.welcomePayload = welcome;
    this.interpolation = new InterpolationBuffer(1000 / welcome.tick_rate, this.options.interpolationDelayMs);
    this.ensurePredictor();
  }

  private ensurePredictor(): void {
    if (this.predictor || !this.grid || !this.welcomePayload) return;
    this.predictor = new LocalPredictor(
      this.grid,
      this.options.movement ?? MOVEMENT,
      1 / this.welcomePayload.tick_rate,
    );
    if (this.pendingServerState) {
      this.predictor.reconcile(this.pendingServerState.ack, this.pendingServerState.pos);
      this.pendingServerState = null;
    }
  }

  private handleSnapshot(
    tick: number,
    ack: number,
    entities: Parameters<InterpolationBuffer['push']>[1],
  ): void {
    const now = this.now();
    const selfId = this.welcomePayload?.entity_id;
    this.visible = entities.length;
    this.interpolation?.push(tick, entities, now, selfId);
    const self = entities.find((e) => e.id === selfId);
    if (!self) return;
    const server = { x: self.x, y: self.y };
    if (!this.predictor) {
      this.pendingServerState = { ack, pos: server };
      return;
    }
    const hadPosition = this.predictor.position !== null;
    const delta = this.predictor.reconcile(ack, server);
    const distance = Math.hypot(delta.x, delta.y);
    if (!hadPosition) return;
    if (distance > 0) {
      this.lastCorrection = distance;
      this.corrections.push({ t: now, d: distance });
    }
    if (distance > SNAP_DISTANCE) {
      // Téléportation : pas de lissage.
      this.previousPos = this.predictor.position;
      this.visualOffset = { x: 0, y: 0 };
    } else if (distance > 0) {
      // Le sprite ne saute pas : la correction est absorbée progressivement.
      if (this.previousPos)
        this.previousPos = { x: this.previousPos.x + delta.x, y: this.previousPos.y + delta.y };
      this.visualOffset = { x: this.visualOffset.x - delta.x, y: this.visualOffset.y - delta.y };
    }
  }

  private decayVisualOffset(elapsedMs: number): void {
    if (this.visualOffset.x === 0 && this.visualOffset.y === 0) return;
    const k = Math.exp(-elapsedMs / CORRECTION_SMOOTHING_MS);
    const x = this.visualOffset.x * k;
    const y = this.visualOffset.y * k;
    this.visualOffset = Math.hypot(x, y) < 1e-4 ? { x: 0, y: 0 } : { x, y };
  }

  private pruneCorrections(now: number): void {
    while (this.corrections.length > 0 && this.corrections[0]!.t < now - CORRECTION_WINDOW_MS) {
      this.corrections.shift();
    }
  }
}
