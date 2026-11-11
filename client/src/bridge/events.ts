// Contrat des événements échangés entre React (HUD, écrans) et Phaser (scènes).
import type { ZoneClient } from '../net/ZoneClient';

export type NetLinkState = 'idle' | 'connecting' | 'open' | 'closed';

/** Vue de l'état réseau poussée par React vers la WorldScene. */
export interface NetStatusView {
  readonly state: NetLinkState;
  readonly zoneId: string | null;
  readonly zoneName: string | null;
  readonly rttMs: number | null;
  readonly serverTick: number | null;
  readonly tickRate: number | null;
  readonly closeCode: number | null;
  /** Libellé lisible de la fermeture, vide si la liaison n'est pas fermée. */
  readonly closeLabel: string;
}

/**
 * Liaison de jeu passée par React à la WorldScene : la scène la pilote à chaque image (entrées,
 * prédiction) et lit les positions à afficher. Logique réseau pure, sans React ni Zustand.
 */
export type ZoneLink = Pick<
  ZoneClient,
  | 'welcome'
  | 'ready'
  | 'setCollisionGrid'
  | 'update'
  | 'getLocalPlayer'
  | 'getRemotePlayers'
  | 'getStats'
  | 'isDead'
  | 'sendAction'
  | 'takeFx'
>;

/** Mesures de jeu poussées par Phaser vers le HUD (quelques fois par seconde). */
export interface GameStatsView {
  /** Position du joueur, en tuiles (null tant qu'elle est inconnue). */
  readonly tileX: number | null;
  readonly tileY: number | null;
  /** Joueurs dans le rayon d'intérêt, joueur local compris. */
  readonly visiblePlayers: number;
  /** Plus forte correction de réconciliation récente, en tuiles. */
  readonly correctionTiles: number;
  /** Étape de chargement affichée tant que le monde n'est pas prêt (vide ensuite). */
  readonly loading: string;
}

// Alias de type (et non interface) pour satisfaire la contrainte `Record<string, unknown>` du bus.
export type BridgeEvents = {
  /** React → Phaser : état de la liaison de zone. */
  'net:status': NetStatusView;
  /** React → Phaser : liaison de jeu de la zone courante (null en quittant). */
  'zone:link': ZoneLink | null;
  /** Phaser → React : position, joueurs visibles, correction. */
  'game:stats': GameStatsView;
  /** Phaser → React : une scène est prête. */
  'game:scene-ready': { readonly scene: string };
};
