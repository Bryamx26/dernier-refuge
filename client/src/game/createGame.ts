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
    pixelArt: true,
    banner: false,
    audio: { noAudio: true },
    scale: {
      mode: Phaser.Scale.RESIZE,
      width: parent.clientWidth || 960,
      height: parent.clientHeight || 540,
    },
    scene: [BootScene, WorldScene],
  });
}
