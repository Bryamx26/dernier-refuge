// Panneau « Terrain » du HUD : position du survivant, joueurs visibles, erreur de réconciliation.
import type { ReactNode } from 'react';
import type { GameStatsView } from '../../bridge';
import { CORRECTION_WARN_TILES, formatCorrection, formatTiles } from './format';

function Row({
  label,
  children,
  testId,
}: {
  readonly label: string;
  readonly children: ReactNode;
  readonly testId?: string;
}) {
  return (
    <div className="flex justify-between gap-6">
      <dt className="text-ash">{label}</dt>
      <dd className="text-right text-bone tabular-nums" data-testid={testId}>
        {children}
      </dd>
    </div>
  );
}

export function WorldPanel({ stats }: { readonly stats: GameStatsView | null }) {
  const correction = stats?.correctionTiles ?? 0;
  const correctionClass = correction >= CORRECTION_WARN_TILES ? 'text-rust-400' : 'text-bone';
  return (
    <section
      aria-label="Terrain"
      className="terminal-frame pointer-events-auto min-w-56 px-3 py-2 text-lg leading-tight"
    >
      <h2 className="mb-1 font-display text-xs tracking-[0.2em] text-verdigris-300 uppercase">Terrain</h2>
      <dl>
        <Row label="Position" testId="world-position">
          {stats && stats.tileX !== null && stats.tileY !== null
            ? `${formatTiles(stats.tileX)} · ${formatTiles(stats.tileY)}`
            : '—'}
        </Row>
        <Row label="Joueurs" testId="world-players">
          {stats ? stats.visiblePlayers : '—'}
        </Row>
        <Row label="Correction" testId="world-correction">
          <span className={correctionClass}>{formatCorrection(correction)}</span>
        </Row>
      </dl>
    </section>
  );
}
