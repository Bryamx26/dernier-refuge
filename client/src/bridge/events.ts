// Contrat des événements échangés entre React (HUD, écrans) et Phaser (scènes).

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

// Alias de type (et non interface) pour satisfaire la contrainte `Record<string, unknown>` du bus.
export type BridgeEvents = {
  /** React → Phaser : état de la liaison de zone. */
  'net:status': NetStatusView;
  /** Phaser → React : une scène est prête. */
  'game:scene-ready': { readonly scene: string };
};
