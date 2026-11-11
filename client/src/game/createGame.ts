// Configuration et création de l'instance Phaser (aucune dépendance à React).
import Phaser from 'phaser';
import { hexToNumber, palette } from '../ui/theme/palette';
import { BootScene } from './scenes/BootScene';
import { WorldScene } from './scenes/WorldScene';

export function createGame(parent: HTMLElement): Phaser.Game {
  return new Phaser.Game({
    type: Phaser.AUTO,
    parent,
    backgroundColor: hexToNumber(palette.charcoal950),
    // Rendu pixel net : filtrage au plus proche et positions arrondies au pixel.
    pixelArt: true,
    roundPixels: true,
    banner: false,
    // Clavier lu par la WorldScene via `event.code` (indépendant AZERTY/QWERTY).
    input: { keyboard: false },
    // Pas de menu contextuel : le clic droit servira au combat (phases suivantes).
    disableContextMenu: true,
    audio: { noAudio: true },
    scale: {
      mode: Phaser.Scale.RESIZE,
      width: parent.clientWidth || 960,
      height: parent.clientHeight || 540,
    },
    scene: [BootScene, WorldScene],
  });
}
