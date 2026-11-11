// Scène d'amorçage : attend les polices pixel (texte Phaser rendu sur canvas) puis lance le monde.
import Phaser from 'phaser';
import { fonts, hexToNumber, palette } from '../../ui/theme/palette';
import { SceneKeys } from '../sceneKeys';

const FONT_LOAD_TIMEOUT_MS = 2000;

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

  create(): void {
    this.cameras.main.setBackgroundColor(hexToNumber(palette.charcoal950));
    let cancelled = false;
    this.events.once(Phaser.Scenes.Events.DESTROY, () => {
      cancelled = true;
    });
    void waitForFonts().then(() => {
      if (!cancelled) this.scene.start(SceneKeys.World);
    });
  }
}
