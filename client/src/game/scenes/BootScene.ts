// Scène d'amorçage : polices pixel (texte Phaser rendu sur canvas), sprites des survivants et
// tileset, puis lancement du monde. La carte elle-même dépend de la zone (welcome) : WorldScene.
import Phaser from 'phaser';
import { fonts, hexToNumber, palette } from '../../ui/theme/palette';
import { SceneKeys } from '../sceneKeys';
import { loadSurvivorTextures, queueSurvivorSheets } from '../sprites/loadSurvivors';
import { GAME_DATA_URL, LOOT_TEXTURE } from '../sprites/survivors';

const FONT_LOAD_TIMEOUT_MS = 2000;
export const TILESET_TEXTURE = 'tileset:valcendre';
export const TILESET_NAME = 'valcendre';

function waitForFonts(): Promise<unknown> {
  if (typeof document === 'undefined' || !('fonts' in document)) return Promise.resolve();
  const loads = Promise.all([
    document.fonts.load(`24px ${fonts.terminal}`),
    document.fonts.load(`24px ${fonts.display}`),
  ]);
  const timeout = new Promise((resolve) => setTimeout(resolve, FONT_LOAD_TIMEOUT_MS));
  return Promise.race([loads, timeout]).catch(() => undefined);
}

export class BootScene extends Phaser.Scene {
  constructor() {
    super(SceneKeys.Boot);
  }

  preload(): void {
    this.cameras.main.setBackgroundColor(hexToNumber(palette.charcoal950));
    this.load.on(Phaser.Loader.Events.FILE_LOAD_ERROR, (file: Phaser.Loader.File) => {
      console.warn(`[assets] Échec du chargement : ${file.url as string}`);
    });
    queueSurvivorSheets(this);
    this.load.image(TILESET_TEXTURE, `${GAME_DATA_URL}/assets/tilesets/${TILESET_NAME}.png`);
    this.load.image(LOOT_TEXTURE, `${GAME_DATA_URL}/assets/sprites/loot.png`);
  }

  create(): void {
    let cancelled = false;
    this.events.once(Phaser.Scenes.Events.DESTROY, () => {
      cancelled = true;
    });
    void Promise.all([waitForFonts(), loadSurvivorTextures(this)]).then(() => {
      if (!cancelled) this.scene.start(SceneKeys.World);
    });
  }
}
