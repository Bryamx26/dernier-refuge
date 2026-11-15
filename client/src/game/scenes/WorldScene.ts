// Scène du monde : carte Tiled de la zone, joueur local prédit, autres joueurs interpolés,
// caméra bornée à zoom entier, voile sombre. La logique réseau vient du bridge (`zone:link`) ;
// aucune dépendance à React ni aux stores.
import Phaser from 'phaser';
import { gameBus, type GameStatsView, type NetStatusView, type ZoneLink } from '../../bridge';
import type { AnimState, EntityKind, FxEvent } from '../../generated/protocol';
import type { RemoteEntityView } from '../../net/interpolation';
import { fonts, hexToNumber, palette } from '../../ui/theme/palette';
import { MovementKeys } from '../input/movementKeys';
import { CollisionGrid, type TiledMapLike } from '../movement/CollisionGrid';
import { SceneKeys } from '../sceneKeys';
import { VARIANTS_REGISTRY_KEY } from '../sprites/loadSurvivors';
import {
  animKey,
  facingFromAim,
  GAME_DATA_URL,
  LOOT_TEXTURE,
  PLACEHOLDER_SPRITE,
  variantForId,
  ZOMBIE_SPRITE,
  type Facing,
} from '../sprites/survivors';
import { TILESET_NAME, TILESET_TEXTURE } from './BootScene';

/** Taille d'une tuile, en pixels monde. */
export const TILE_PX = 16;
export const DEFAULT_ZOOM = 3;
const STATS_INTERVAL_MS = 200;

/** Profondeurs d'affichage : sol < décor < sang < objets < personnages (triés par y) < effets < `above`. */
const DEPTH = { ground: 0, decor: 1, blood: 2, items: 3, actors: 10, effects: 9_000, above: 10_000 } as const;
/** Distance (tuiles) sous laquelle le nom d'un objet au sol s'affiche. */
const ITEM_LABEL_RANGE = 2;
/** Durée de vie des effets (ms). */
const FX_TTL: Record<FxEvent['kind'], number> = { shot: 90, swing: 140, hit: 180, blood: 9000, search: 400 };
/** Touches d'action (position physique) → action envoyée au serveur. */
const ACTION_CODES: Readonly<Record<string, 'interact' | 'reload'>> = { KeyE: 'interact', KeyR: 'reload' };
/** Profondeurs de la couche d'interface (caméra non zoomée). */
const UI_DEPTH = { veil: 0, vignette: 1, names: 2, status: 3 } as const;

/** Calques affichés ; `collision` ne l'est jamais. */
const VISIBLE_LAYERS = [
  { name: 'ground', depth: DEPTH.ground },
  { name: 'decor', depth: DEPTH.decor },
  { name: 'above', depth: DEPTH.above },
] as const;

/** Zoom entier adapté à l'écran : 3 par défaut, 2 sur un petit écran. */
export function pickZoom(width: number, height: number): number {
  return Math.min(width, height) < 520 ? 2 : DEFAULT_ZOOM;
}

/** Abscisse (ou ordonnée) gauche de la vue, bornée à la carte, en pixels monde entiers. */
export function clampView(center: number, view: number, world: number): number {
  if (world <= view) return Math.round((world - view) / 2);
  return Math.round(Math.min(Math.max(center - view / 2, 0), world - view));
}

interface Actor {
  readonly kind: EntityKind;
  readonly sprite: Phaser.GameObjects.Sprite;
  readonly variant: string;
  readonly label: Phaser.GameObjects.Text | null;
  facing: Facing;
  anim: AnimState;
  health: number;
}

interface ActiveFx {
  readonly event: FxEvent;
  readonly born: number;
}

type Phase = 'waiting' | 'loading-map' | 'ready' | 'map-error';

export class WorldScene extends Phaser.Scene {
  private link: ZoneLink | null = null;
  private phase: Phase = 'waiting';
  private mapKey = '';
  private mapSize = { w: 0, h: 0 };
  private zoom = DEFAULT_ZOOM;
  private view = { x: 0, y: 0 };
  private uiCamera!: Phaser.Cameras.Scene2D.Camera;
  private veil!: Phaser.GameObjects.Rectangle;
  private vignette!: Phaser.GameObjects.Image;
  private statusText!: Phaser.GameObjects.Text;
  private readonly keys = new MovementKeys();
  private local: Actor | null = null;
  private readonly remotes = new Map<string, Actor>();
  private aim = Math.PI / 2;
  private pointerActive = false;
  private lastStatsAt = 0;
  private attackHeld = false;
  private effects: ActiveFx[] = [];
  private overlay!: Phaser.GameObjects.Graphics;
  private groundFx!: Phaser.GameObjects.Graphics;
  private netState: NetStatusView['state'] = 'idle';

  constructor() {
    super(SceneKeys.World);
  }

  create(): void {
    this.phase = 'waiting';
    this.cameras.main.setBackgroundColor(hexToNumber(palette.charcoal950));
    this.cameras.main.setRoundPixels(true);
    // Caméra d'interface non zoomée : voile, vignette, noms, messages (texte net à toute échelle).
    this.uiCamera = this.cameras.add(0, 0, this.scale.width, this.scale.height, false, 'ui');

    this.veil = this.addUi(
      this.add.rectangle(0, 0, 1, 1, 0x7d8c86).setOrigin(0).setBlendMode(Phaser.BlendModes.MULTIPLY),
    ).setDepth(UI_DEPTH.veil);
    this.vignette = this.addUi(this.add.image(0, 0, this.createVignetteTexture()).setOrigin(0)).setDepth(
      UI_DEPTH.vignette,
    );
    this.statusText = this.addUi(
      this.add
        .text(0, 0, '', {
          fontFamily: fonts.terminal,
          fontSize: '28px',
          color: palette.bone,
          align: 'center',
          lineSpacing: 4,
        })
        .setOrigin(0.5)
        .setShadow(2, 2, '#000000', 0, false, true),
    ).setDepth(UI_DEPTH.status);

    this.overlay = this.addWorld(this.add.graphics()).setDepth(DEPTH.effects);
    this.groundFx = this.addWorld(this.add.graphics()).setDepth(DEPTH.blood);

    this.input.on(Phaser.Input.Events.POINTER_MOVE, () => {
      this.pointerActive = true;
    });
    this.input.on(Phaser.Input.Events.POINTER_DOWN, (pointer: Phaser.Input.Pointer) => {
      this.pointerActive = true;
      if (pointer.leftButtonDown()) this.attackHeld = true;
    });
    this.input.on(Phaser.Input.Events.POINTER_UP, (pointer: Phaser.Input.Pointer) => {
      if (!pointer.leftButtonDown()) this.attackHeld = false;
    });
    this.input.on(Phaser.Input.Events.GAME_OUT, () => {
      this.pointerActive = false;
      this.attackHeld = false;
    });
    window.addEventListener('keydown', this.onKeyDown);
    window.addEventListener('keyup', this.onKeyUp);
    window.addEventListener('blur', this.onBlur);

    const offLink = gameBus.on('zone:link', (link) => this.attach(link));
    const offNet = gameBus.on('net:status', (view) => {
      this.netState = view.state;
    });
    this.netState = gameBus.last('net:status')?.state ?? 'idle';
    this.scale.on(Phaser.Scale.Events.RESIZE, this.layout);
    this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => {
      offLink();
      offNet();
      this.scale.off(Phaser.Scale.Events.RESIZE, this.layout);
      window.removeEventListener('keydown', this.onKeyDown);
      window.removeEventListener('keyup', this.onKeyUp);
      window.removeEventListener('blur', this.onBlur);
    });

    this.layout();
    this.attach(gameBus.last('zone:link') ?? null);
    gameBus.emit('game:scene-ready', { scene: SceneKeys.World });
  }

  override update(): void {
    const now = performance.now();
    const link = this.link;
    if (link && this.phase === 'waiting' && link.welcome) this.loadMap(link.welcome.map_id);

    if (link && this.phase === 'ready') {
      const axes = this.keys.axes();
      const localView = link.getLocalPlayer();
      if (localView) this.updateAim(localView.x, localView.y, axes.moveX, axes.moveY);
      link.update(now, {
        move_x: axes.moveX,
        move_y: axes.moveY,
        sprint: axes.sprint,
        aim: this.aim,
        attack: this.attackHeld,
      });
      this.renderActors(link, now);
      this.renderEffects(link, now);
    }
    this.statusText.setText(this.statusMessage());
    if (now - this.lastStatsAt >= STATS_INTERVAL_MS) {
      this.lastStatsAt = now;
      gameBus.emit('game:stats', this.stats(now));
    }
  }

  // --- Liaison et carte -------------------------------------------------------------------

  private attach(link: ZoneLink | null): void {
    this.link = link;
  }

  private loadMap(mapId: string): void {
    this.phase = 'loading-map';
    this.mapKey = `map:${mapId}`;
    if (this.cache.tilemap.exists(this.mapKey)) {
      this.buildMap();
      return;
    }
    const onError = (file: Phaser.Loader.File) => {
      if (file.key === this.mapKey) this.phase = 'map-error';
    };
    this.load.on(Phaser.Loader.Events.FILE_LOAD_ERROR, onError);
    this.load.tilemapTiledJSON(this.mapKey, `${GAME_DATA_URL}/maps/${encodeURIComponent(mapId)}.tmj`);
    this.load.once(Phaser.Loader.Events.COMPLETE, () => {
      this.load.off(Phaser.Loader.Events.FILE_LOAD_ERROR, onError);
      if (this.phase === 'loading-map') this.buildMap();
    });
    this.load.start();
  }

  private buildMap(): void {
    const raw = (this.cache.tilemap.get(this.mapKey) as { data?: TiledMapLike } | undefined)?.data;
    if (!raw) {
      this.phase = 'map-error';
      return;
    }
    let grid: CollisionGrid;
    try {
      grid = CollisionGrid.fromTiledMap(raw);
    } catch (error) {
      console.error('[carte]', error);
      this.phase = 'map-error';
      return;
    }
    const map = this.make.tilemap({ key: this.mapKey });
    const tileset = map.addTilesetImage(TILESET_NAME, TILESET_TEXTURE);
    if (!tileset) {
      console.error(`[carte] Tileset « ${TILESET_NAME} » absent de la carte ou de l'image`);
      this.phase = 'map-error';
      return;
    }
    for (const { name, depth } of VISIBLE_LAYERS) {
      const layer = map.createLayer(name, tileset, 0, 0);
      if (layer) this.addWorld(layer.setDepth(depth));
      else console.warn(`[carte] Calque « ${name} » absent`);
    }
    this.mapSize = { w: map.widthInPixels, h: map.heightInPixels };
    this.cameras.main.setBounds(0, 0, this.mapSize.w, this.mapSize.h);
    this.link?.setCollisionGrid(grid);
    this.phase = 'ready';
    this.layout();
  }

  // --- Personnages ------------------------------------------------------------------------

  private renderActors(link: ZoneLink, now: number): void {
    const local = link.getLocalPlayer();
    if (local) {
      this.local ??= this.createActor({ ...local, kind: 'player', name: '', health: 1 }, false);
      this.placeActor(this.local, local.x, local.y, local.aim, local.anim);
      this.followCamera(local.x * TILE_PX, local.y * TILE_PX);
    }

    const seen = new Set<string>();
    for (const remote of link.getRemotePlayers(now)) {
      seen.add(remote.id);
      let actor = this.remotes.get(remote.id);
      if (!actor) {
        actor = this.createActor(remote, remote.kind !== 'zombie');
        this.remotes.set(remote.id, actor);
      }
      actor.health = remote.health;
      this.placeActor(actor, remote.x, remote.y, remote.aim, remote.anim);
    }
    for (const [id, actor] of this.remotes) {
      if (seen.has(id)) continue;
      actor.sprite.destroy();
      actor.label?.destroy();
      this.remotes.delete(id);
    }
    // Les noms suivent les sprites, en coordonnées écran (caméra d'interface). Celui d'un objet au
    // sol n'apparaît qu'à proximité du joueur.
    for (const actor of this.remotes.values()) {
      if (actor.kind === 'item' && actor.label) {
        const near =
          local !== null &&
          Math.hypot(actor.sprite.x / TILE_PX - local.x, actor.sprite.y / TILE_PX - local.y) <=
            ITEM_LABEL_RANGE;
        actor.label.setVisible(near);
        if (!near) continue;
      }
      this.placeLabel(actor);
    }
  }

  private createActor(
    view: Pick<RemoteEntityView, 'id' | 'kind' | 'name' | 'health'>,
    withLabel: boolean,
  ): Actor {
    const variants = (this.registry.get(VARIANTS_REGISTRY_KEY) as string[] | undefined) ?? [
      PLACEHOLDER_SPRITE,
    ];
    let variant: string;
    if (view.kind === 'zombie')
      variant = this.textures.exists(ZOMBIE_SPRITE) ? ZOMBIE_SPRITE : PLACEHOLDER_SPRITE;
    else if (view.kind === 'item')
      variant = this.textures.exists(LOOT_TEXTURE) ? LOOT_TEXTURE : PLACEHOLDER_SPRITE;
    else variant = variantForId(view.id, variants);
    const sprite = this.addWorld(this.add.sprite(0, 0, variant, view.kind === 'item' ? undefined : 0));
    const name = withLabel ? view.name : null;
    let label: Phaser.GameObjects.Text | null = null;
    if (name !== null) {
      label = this.addUi(
        this.add
          .text(0, 0, name, {
            fontFamily: fonts.terminal,
            color: view.kind === 'item' ? palette.ash : palette.bone,
            fontSize: view.kind === 'item' ? '18px' : '20px',
            stroke: '#000000',
            strokeThickness: 4,
          })
          .setOrigin(0.5, 1)
          .setDepth(UI_DEPTH.names),
      );
    }
    return { kind: view.kind, sprite, variant, label, facing: 'down', anim: 'idle', health: view.health };
  }

  private placeActor(actor: Actor, x: number, y: number, aim: number, anim: AnimState): void {
    // Arrondi au pixel monde : rendu net, pas de demi-pixels.
    actor.sprite.setPosition(Math.round(x * TILE_PX), Math.round(y * TILE_PX));
    if (actor.kind === 'item') {
      actor.sprite.setDepth(DEPTH.items);
      return;
    }
    const dead = anim === 'dead';
    // Un mort est couché (et passe sous les vivants) ; un zombie qui frappe rougit un instant.
    actor.sprite.setDepth(dead ? DEPTH.items + 0.5 : DEPTH.actors + y / 1000);
    actor.sprite.setAngle(dead ? 90 : 0);
    if (dead) actor.sprite.setTint(0x8a7070);
    else if (anim === 'attack') actor.sprite.setTint(0xffb0a0);
    else actor.sprite.clearTint();
    const facing = facingFromAim(aim);
    if (facing !== actor.facing || anim !== actor.anim || !actor.sprite.anims.isPlaying) {
      actor.facing = facing;
      actor.anim = anim;
      const key = animKey(actor.variant, anim, facing);
      if (this.anims.exists(key)) actor.sprite.play(key, true);
    }
  }

  /** Effets (tirs, coups, impacts, sang) et barres de vie des zombies blessés. */
  private renderEffects(link: ZoneLink, now: number): void {
    for (const event of link.takeFx()) this.effects.push({ event, born: now });
    this.effects = this.effects.filter((fx) => now - fx.born < FX_TTL[fx.event.kind]);
    const g = this.overlay;
    const ground = this.groundFx;
    g.clear();
    ground.clear();
    for (const { event, born } of this.effects) {
      const life = 1 - (now - born) / FX_TTL[event.kind];
      const x = event.x * TILE_PX;
      const y = event.y * TILE_PX;
      switch (event.kind) {
        case 'shot':
          g.lineStyle(1, 0xffe08a, 0.9 * life);
          g.lineBetween(x, y, event.x2 * TILE_PX, event.y2 * TILE_PX);
          g.fillStyle(0xfff2c0, life);
          g.fillCircle(x + (event.x2 - event.x) * 4, y + (event.y2 - event.y) * 4, 1.5);
          break;
        case 'swing':
          g.lineStyle(1, 0xe8e4d8, 0.8 * life);
          g.lineBetween(x, y, event.x2 * TILE_PX, event.y2 * TILE_PX);
          break;
        case 'hit':
          g.fillStyle(0xc0392b, 0.85 * life);
          g.fillCircle(x, y, 3 + 2 * (1 - life));
          break;
        case 'blood':
          ground.fillStyle(0x5a1010, 0.7 * Math.min(1, life * 3));
          ground.fillCircle(x, y + 4, 3);
          ground.fillCircle(x + 3, y + 6, 2);
          break;
        case 'search':
          g.lineStyle(1, 0xd9cfa8, life);
          g.strokeCircle(x, y, 6 + 6 * (1 - life));
          break;
      }
    }
    for (const actor of this.remotes.values()) {
      if (actor.kind !== 'zombie' || actor.health >= 1 || actor.anim === 'dead') continue;
      const bx = actor.sprite.x - 6;
      const by = actor.sprite.y - 11;
      g.fillStyle(0x000000, 0.7);
      g.fillRect(bx - 1, by - 1, 14, 3);
      g.fillStyle(0xc0392b, 1);
      g.fillRect(bx, by, Math.max(1, Math.round(12 * actor.health)), 1);
    }
  }

  private placeLabel(actor: Actor): void {
    if (!actor.label) return;
    const top = actor.sprite.y - actor.sprite.displayHeight * actor.sprite.originY;
    actor.label.setPosition(
      Math.round((actor.sprite.x - this.view.x) * this.zoom),
      Math.round((top - this.view.y) * this.zoom) - 2,
    );
  }

  // --- Caméra et entrées ------------------------------------------------------------------

  /** Centre la vue sur le joueur, bornée à la carte, en pixels monde entiers. */
  private followCamera(px: number, py: number): void {
    const cam = this.cameras.main;
    const viewW = cam.width / this.zoom;
    const viewH = cam.height / this.zoom;
    this.view = { x: clampView(px, viewW, this.mapSize.w), y: clampView(py, viewH, this.mapSize.h) };
    // Phaser : worldView.x = scrollX + width/2 − width/(2 zoom).
    cam.setScroll(this.view.x - cam.width / 2 + viewW / 2, this.view.y - cam.height / 2 + viewH / 2);
  }

  private updateAim(x: number, y: number, moveX: number, moveY: number): void {
    const pointer = this.input.activePointer;
    if (this.pointerActive) {
      const wx = this.view.x + pointer.x / this.zoom;
      const wy = this.view.y + pointer.y / this.zoom;
      const dx = wx - x * TILE_PX;
      const dy = wy - y * TILE_PX;
      if (dx !== 0 || dy !== 0) this.aim = Math.atan2(dy, dx);
    } else if (moveX !== 0 || moveY !== 0) {
      this.aim = Math.atan2(moveY, moveX);
    }
  }

  private readonly onKeyDown = (event: KeyboardEvent): void => {
    if (isTextTarget(event.target)) return;
    if (this.keys.keyDown(event)) {
      event.preventDefault();
      return;
    }
    if (event.repeat || event.ctrlKey || event.metaKey || event.altKey || !this.link) return;
    const action = ACTION_CODES[event.code];
    if (action) {
      this.link.sendAction(action);
      event.preventDefault();
      return;
    }
    // Touches 1 à 9 : utiliser / équiper l'emplacement correspondant de l'inventaire.
    const digit = /^Digit([1-9])$/.exec(event.code);
    if (digit) {
      this.link.sendAction('use', Number(digit[1]) - 1);
      event.preventDefault();
    }
  };

  private readonly onKeyUp = (event: KeyboardEvent): void => {
    this.keys.keyUp(event);
  };

  private readonly onBlur = (): void => {
    this.keys.reset();
    this.attackHeld = false;
  };

  // --- Interface ---------------------------------------------------------------------------

  private statusMessage(): string {
    if (this.netState === 'closed') return this.phase === 'ready' ? '' : 'LIAISON PERDUE';
    switch (this.phase) {
      case 'waiting':
        return this.link ? 'CONNEXION À LA ZONE…' : 'EN ATTENTE DU TERMINAL…';
      case 'loading-map':
        return 'CHARGEMENT DE LA CARTE…';
      case 'map-error':
        return 'CARTE INTROUVABLE\nLes données de la zone ne sont pas disponibles.';
      case 'ready':
        return this.link?.ready ? '' : 'LOCALISATION DU SURVIVANT…';
    }
  }

  private stats(now: number): GameStatsView {
    const stats = this.link?.getStats(now);
    const position = stats?.position ?? null;
    const message = this.statusMessage();
    return {
      tileX: position ? position.x : null,
      tileY: position ? position.y : null,
      visiblePlayers: stats?.visiblePlayers ?? 0,
      correctionTiles: stats?.correctionTiles ?? 0,
      loading: message.split('\n')[0] ?? '',
    };
  }

  /** Vignette : dégradé radial précalculé une fois (aucun shader). */
  private createVignetteTexture(): string {
    const key = 'fx:vignette';
    if (this.textures.exists(key)) return key;
    const size = 256;
    const texture = this.textures.createCanvas(key, size, size);
    if (!texture) return key;
    const ctx = texture.getContext();
    const gradient = ctx.createRadialGradient(
      size / 2,
      size / 2,
      size * 0.22,
      size / 2,
      size / 2,
      size * 0.72,
    );
    gradient.addColorStop(0, 'rgba(6, 9, 8, 0)');
    gradient.addColorStop(0.55, 'rgba(6, 9, 8, 0.35)');
    gradient.addColorStop(1, 'rgba(6, 9, 8, 0.9)');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, size, size);
    texture.refresh();
    return key;
  }

  // Fonction fléchée : passée telle quelle comme écouteur de redimensionnement.
  private readonly layout = (): void => {
    const { width, height } = this.scale.gameSize;
    this.zoom = pickZoom(width, height);
    this.cameras.main.setZoom(this.zoom);
    this.uiCamera.setSize(width, height);
    this.veil.setSize(width, height);
    this.vignette.setDisplaySize(width, height);
    this.statusText.setPosition(Math.round(width / 2), Math.round(height / 2));
  };

  /** Objet du monde : vu par la caméra principale seulement. */
  private addWorld<T extends Phaser.GameObjects.GameObject>(object: T): T {
    this.uiCamera.ignore(object);
    return object;
  }

  /** Objet d'interface : vu par la caméra non zoomée seulement. */
  private addUi<T extends Phaser.GameObjects.GameObject>(object: T): T {
    this.cameras.main.ignore(object);
    return object;
  }
}

function isTextTarget(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement
  );
}
