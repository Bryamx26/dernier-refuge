// Chargement Phaser des planches de survivants et création de leurs animations.
// Si un asset manque, un sprite PLACEHOLDER (texture générée, nommée `survivor_PLACEHOLDER`) le remplace.
import Phaser from 'phaser';
import {
  animKey,
  isSurvivorSheet,
  PLACEHOLDER_SPRITE,
  spriteUrls,
  SURVIVOR_VARIANTS,
  type Facing,
  type SurvivorSheet,
} from './survivors';

const FACINGS: readonly Facing[] = ['down', 'left', 'right', 'up'];
const STATES = ['idle', 'walk', 'run'] as const;
export const VARIANTS_REGISTRY_KEY = 'survivorVariants';

const sheetKey = (variant: string) => `${variant}:sheet`;

/** À appeler dans `preload()` : met en file les descriptions JSON. */
export function queueSurvivorSheets(scene: Phaser.Scene): void {
  for (const variant of SURVIVOR_VARIANTS) scene.load.json(sheetKey(variant), spriteUrls(variant).json);
}

/**
 * À appeler dans `create()` : charge les images décrites par les JSON reçus, crée les animations,
 * puis renvoie (via la promesse) la liste des variantes réellement disponibles.
 */
export function loadSurvivorTextures(scene: Phaser.Scene): Promise<string[]> {
  const sheets = new Map<string, SurvivorSheet>();
  for (const variant of SURVIVOR_VARIANTS) {
    const data: unknown = scene.cache.json.get(sheetKey(variant));
    if (isSurvivorSheet(data)) {
      sheets.set(variant, data);
      scene.load.spritesheet(variant, spriteUrls(variant).png, {
        frameWidth: data.frameWidth,
        frameHeight: data.frameHeight,
      });
    }
  }
  return new Promise((resolve) => {
    const finish = () => {
      const available: string[] = [];
      for (const [variant, sheet] of sheets) {
        if (!scene.textures.exists(variant)) continue;
        createAnimations(scene, variant, sheet);
        available.push(variant);
      }
      createPlaceholder(scene);
      if (available.length < SURVIVOR_VARIANTS.length) {
        console.warn(
          `[assets] Variantes de survivant manquantes : ${SURVIVOR_VARIANTS.filter((v) => !available.includes(v)).join(', ')}`,
        );
      }
      scene.registry.set(VARIANTS_REGISTRY_KEY, available.length > 0 ? available : [PLACEHOLDER_SPRITE]);
      resolve(available);
    };
    if (sheets.size === 0) {
      finish();
      return;
    }
    scene.load.once(Phaser.Loader.Events.COMPLETE, finish);
    scene.load.start();
  });
}

function createAnimations(scene: Phaser.Scene, variant: string, sheet: SurvivorSheet): void {
  for (const state of STATES) {
    for (const facing of FACINGS) {
      const def = sheet.animations[`${state}_${facing}`];
      const key = animKey(variant, state, facing);
      if (!def || scene.anims.exists(key)) continue;
      scene.anims.create({
        key,
        frames: def.frames.map((frame) => ({ key: variant, frame })),
        frameRate: def.fps,
        repeat: def.loop ? -1 : 0,
      });
    }
  }
}

// PLACEHOLDER : silhouette magenta avec « ? », 16 × 16, pour signaler un asset manquant à l'écran.
const PLACEHOLDER_ART = [
  '.....######.....',
  '....#MMMMMM#....',
  '...#MMWWWWMM#...',
  '...#MWMMMMWM#...',
  '...#MMMMMWWM#...',
  '...#MMMWWMMM#...',
  '....#MMWWMM#....',
  '.....#MMMM#.....',
  '...##MMMMMM##...',
  '..#MMMMWWMMMM#..',
  '..#M#MMWWMM#M#..',
  '..##.#MMMM#.##..',
  '.....#MMMM#.....',
  '.....#MM#MM#....',
  '....#MM#.#MM#...',
  '....###...###...',
];
const PLACEHOLDER_COLORS: Record<string, string> = { '#': '#000000', M: '#ff00ff', W: '#ffffff' };

function createPlaceholder(scene: Phaser.Scene): void {
  if (scene.textures.exists(PLACEHOLDER_SPRITE)) return;
  const texture = scene.textures.createCanvas(PLACEHOLDER_SPRITE, 16, 16);
  if (!texture) return;
  const ctx = texture.getContext();
  PLACEHOLDER_ART.forEach((row, y) => {
    for (let x = 0; x < row.length; x += 1) {
      const color = PLACEHOLDER_COLORS[row[x]!];
      if (!color) continue;
      ctx.fillStyle = color;
      ctx.fillRect(x, y, 1, 1);
    }
  });
  texture.refresh();
  for (const state of STATES) {
    for (const facing of FACINGS) {
      scene.anims.create({
        key: animKey(PLACEHOLDER_SPRITE, state, facing),
        frames: [{ key: PLACEHOLDER_SPRITE, frame: '__BASE' }],
        frameRate: 1,
        repeat: -1,
      });
    }
  }
}
