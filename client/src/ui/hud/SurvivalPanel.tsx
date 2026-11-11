// Jauges de survie (santé, faim, soif), saignement, arme en main et action en cours.
import type { InventoryPayload, VitalsPayload } from '../../generated/protocol';

function Gauge({
  label,
  value,
  max,
  color,
  testId,
}: {
  readonly label: string;
  readonly value: number;
  readonly max: number;
  readonly color: string;
  readonly testId: string;
}) {
  const ratio = max > 0 ? Math.max(0, Math.min(1, value / max)) : 0;
  const low = ratio < 0.25;
  return (
    <div className="grid grid-cols-[4.5rem_1fr_2.5rem] items-center gap-2">
      <span className={low ? 'text-rust-400' : 'text-ash'}>{label}</span>
      <div className="h-2.5 border border-charcoal-600 bg-charcoal-950">
        <div
          className="h-full transition-[width] duration-200"
          style={{ width: `${ratio * 100}%`, background: low ? 'var(--color-rust-400)' : color }}
        />
      </div>
      <span className="text-right text-bone tabular-nums" data-testid={testId}>
        {Math.round(value)}
      </span>
    </div>
  );
}

export function SurvivalPanel({
  vitals,
  inventory,
}: {
  readonly vitals: VitalsPayload | null;
  readonly inventory: InventoryPayload | null;
}) {
  if (!vitals) return null;
  const weapon = inventory?.slots.find((s) => s.slot === inventory.equipped) ?? null;
  const ammo =
    weapon?.kind === 'firearm'
      ? inventory!.slots.filter((s) => s.kind === 'ammo').reduce((sum, s) => sum + s.qty, 0)
      : null;
  return (
    <section
      aria-label="Survie"
      className="terminal-frame pointer-events-auto w-72 px-3 py-2 text-lg leading-tight"
    >
      <h2 className="mb-1 flex justify-between font-display text-xs tracking-[0.2em] text-verdigris-300 uppercase">
        <span>Survie</span>
        {vitals.bleeding && (
          <span className="animate-pulse text-rust-400" data-testid="bleeding">
            Saignement
          </span>
        )}
      </h2>
      <div className="flex flex-col gap-1">
        <Gauge
          label="Santé"
          value={vitals.health}
          max={vitals.max_health}
          color="#a64b2a"
          testId="vital-health"
        />
        <Gauge label="Faim" value={vitals.hunger} max={100} color="#c9a14a" testId="vital-hunger" />
        <Gauge label="Soif" value={vitals.thirst} max={100} color="#5f8a76" testId="vital-thirst" />
      </div>
      <div className="mt-2 flex justify-between gap-2 border-t border-charcoal-600 pt-1">
        <span className="text-ash">En main</span>
        <span className="text-right text-bone" data-testid="weapon">
          {weapon ? weapon.name : 'Poings'}
          {weapon?.kind === 'firearm' && (
            <span className="ml-2 tabular-nums text-amber">
              {weapon.loaded} / {ammo}
            </span>
          )}
        </span>
      </div>
    </section>
  );
}

/** Barre d'avancement d'une action longue (fouille, rechargement). */
export function ActionProgress({ vitals }: { readonly vitals: VitalsPayload | null }) {
  if (!vitals?.action) return null;
  return (
    <div className="pointer-events-none absolute inset-x-0 top-[58%] flex justify-center">
      <div className="terminal-frame w-64 px-3 py-1 text-center" data-testid="action-progress">
        <div className="text-bone">{vitals.action}</div>
        <div className="mt-1 h-2 border border-charcoal-600 bg-charcoal-950">
          <div className="h-full bg-verdigris-500" style={{ width: `${vitals.action_progress * 100}%` }} />
        </div>
      </div>
    </div>
  );
}
