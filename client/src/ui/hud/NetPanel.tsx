// Panneau réseau du HUD : état de la liaison, ping lissé, tick serveur, zone.
import type { ReactNode } from 'react';
import type { NetStatusView } from '../../bridge';

const STATE_LABELS: Record<NetStatusView['state'], { label: string; className: string }> = {
  idle: { label: 'En attente', className: 'text-ash' },
  connecting: { label: 'Connexion…', className: 'text-amber' },
  open: { label: 'En ligne', className: 'text-verdigris-400' },
  closed: { label: 'Hors ligne', className: 'text-rust-400' },
};

function Row({ label, children }: { readonly label: string; readonly children: ReactNode }) {
  return (
    <div className="flex justify-between gap-6">
      <dt className="text-ash">{label}</dt>
      <dd className="text-right text-bone tabular-nums">{children}</dd>
    </div>
  );
}

export function NetPanel({ view }: { readonly view: NetStatusView }) {
  const state = STATE_LABELS[view.state];
  return (
    <section
      aria-label="Liaison réseau"
      className="terminal-frame pointer-events-auto min-w-56 px-3 py-2 text-lg leading-tight"
    >
      <h2 className="mb-1 font-display text-xs tracking-[0.2em] text-verdigris-300 uppercase">Liaison</h2>
      <dl>
        <Row label="État">
          <span className={state.className} data-testid="net-state">
            {state.label}
          </span>
        </Row>
        <Row label="Ping">{view.rttMs === null ? '—' : `${Math.round(view.rttMs)} ms`}</Row>
        <Row label="Tick">{view.serverTick ?? '—'}</Row>
        <Row label="Zone">{view.zoneName ?? view.zoneId ?? '—'}</Row>
        {view.tickRate !== null && <Row label="Fréquence">{view.tickRate} Hz</Row>}
      </dl>
      {view.state === 'closed' && view.closeLabel && (
        <p className="mt-1 max-w-56 text-base text-rust-400">
          {view.closeLabel}
          {view.closeCode !== null && <span className="text-ash"> [{view.closeCode}]</span>}
        </p>
      )}
    </section>
  );
}
