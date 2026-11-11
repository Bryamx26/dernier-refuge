// Scène du monde — phase 1 : fond sombre et état de la liaison réseau reçu via le bridge.
// Pas de carte ni de personnage avant la phase 2.
import Phaser from 'phaser';
import { gameBus, type NetStatusView } from '../../bridge';
import { fonts, hexToNumber, palette } from '../../ui/theme/palette';
import { SceneKeys } from '../sceneKeys';

const STATE_LABELS: Record<NetStatusView['state'], string> = {
  idle: 'EN ATTENTE',
  connecting: 'CONNEXION…',
  open: 'EN LIGNE',
  closed: 'HORS LIGNE',
};

const STATE_COLORS: Record<NetStatusView['state'], string> = {
  idle: palette.ash,
  connecting: palette.amber,
  open: palette.verdigris400,
  closed: palette.rust400,
};

export function formatStatusLines(view: NetStatusView | undefined): string[] {
  if (!view) return ['LIAISON', '', 'EN ATTENTE DU TERMINAL…'];
  const lines = [
    `ZONE   ${view.zoneName ?? view.zoneId ?? '—'}`,
    `ÉTAT   ${STATE_LABELS[view.state]}`,
    `PING   ${view.rttMs === null ? '—' : `${Math.round(view.rttMs)} ms`}`,
    `TICK   ${view.serverTick ?? '—'}`,
  ];
  if (view.state === 'closed' && view.closeLabel) lines.push('', view.closeLabel.toUpperCase());
  return lines;
}

export class WorldScene extends Phaser.Scene {
  private title!: Phaser.GameObjects.Text;
  private statusText!: Phaser.GameObjects.Text;
  private cursor!: Phaser.GameObjects.Text;

  constructor() {
    super(SceneKeys.World);
  }

  create(): void {
    this.cameras.main.setBackgroundColor(hexToNumber(palette.charcoal950));

    this.title = this.add
      .text(0, 0, 'DERNIER REFUGE — LIAISON DE ZONE', {
        fontFamily: fonts.display,
        fontSize: '20px',
        color: palette.verdigris500,
      })
      .setOrigin(0.5, 1)
      .setLetterSpacing(4);

    this.statusText = this.add
      .text(0, 0, '', {
        fontFamily: fonts.terminal,
        fontSize: '28px',
        color: palette.bone,
        lineSpacing: 6,
      })
      .setOrigin(0.5, 0);

    this.cursor = this.add.text(0, 0, '_', {
      fontFamily: fonts.terminal,
      fontSize: '28px',
      color: palette.verdigris400,
    });
    this.tweens.add({
      targets: this.cursor,
      alpha: 0,
      duration: 550,
      yoyo: true,
      repeat: -1,
      ease: 'Stepped',
    });

    this.applyStatus(gameBus.last('net:status'));
    const unsubscribe = gameBus.on('net:status', (view) => this.applyStatus(view));
    this.scale.on(Phaser.Scale.Events.RESIZE, this.layout);
    this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => {
      unsubscribe();
      this.scale.off(Phaser.Scale.Events.RESIZE, this.layout);
    });

    this.layout();
    gameBus.emit('game:scene-ready', { scene: SceneKeys.World });
  }

  private applyStatus(view: NetStatusView | undefined): void {
    this.statusText.setText(formatStatusLines(view));
    this.statusText.setColor(view ? STATE_COLORS[view.state] : palette.ash);
    this.layout();
  }

  // Fonction fléchée : passée telle quelle comme écouteur de redimensionnement.
  private readonly layout = (): void => {
    const { width, height } = this.scale.gameSize;
    const cx = Math.round(width / 2);
    const cy = Math.round(height / 2);
    this.title.setPosition(cx, cy - 70);
    this.statusText.setPosition(cx, cy - 50);
    const bounds = this.statusText.getBounds();
    this.cursor.setPosition(Math.round(bounds.right + 4), Math.round(bounds.bottom - 34));
  };
}
