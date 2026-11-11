// Inventaire : emplacements, poids, équipement. Les actions passent par le serveur (message `action`).
import type { InventoryPayload, InventorySlot, ItemKind } from '../../generated/protocol';

const KIND_LABELS: Record<ItemKind, string> = {
  melee: 'Mêlée',
  firearm: 'Arme à feu',
  ammo: 'Munitions',
  food: 'Nourriture',
  drink: 'Boisson',
  medical: 'Soins',
};

function actionLabel(slot: InventorySlot, equipped: boolean): string | null {
  if (slot.kind === 'melee' || slot.kind === 'firearm') return equipped ? 'Ranger' : 'Équiper';
  if (slot.kind === 'ammo') return null;
  return slot.kind === 'medical' ? 'Soigner' : slot.kind === 'food' ? 'Manger' : 'Boire';
}

export function InventoryPanel({
  inventory,
  onUse,
  onDrop,
  onClose,
}: {
  readonly inventory: InventoryPayload | null;
  readonly onUse: (slot: number) => void;
  readonly onDrop: (slot: number) => void;
  readonly onClose: () => void;
}) {
  if (!inventory) return null;
  const heavy = inventory.weight > inventory.max_weight * 0.9;
  return (
    <section
      aria-label="Inventaire"
      className="terminal-frame pointer-events-auto w-[26rem] max-w-[calc(100vw-2rem)] text-lg leading-tight"
      data-testid="inventory"
    >
      <header className="flex items-center justify-between border-b-2 border-charcoal-600 bg-charcoal-700/60 px-3 py-1">
        <h2 className="font-display text-sm tracking-[0.2em] text-verdigris-300 uppercase">Inventaire</h2>
        <span className={heavy ? 'text-rust-400' : 'text-ash'}>
          {inventory.weight.toFixed(1)} / {inventory.max_weight} kg · {inventory.slots.length}/
          {inventory.capacity}
        </span>
        <button
          type="button"
          onClick={onClose}
          className="ml-2 px-1 text-ash hover:text-bone"
          aria-label="Fermer l'inventaire"
        >
          ×
        </button>
      </header>
      {inventory.slots.length === 0 ? (
        <p className="px-3 py-3 text-ash">Rien sur vous. Fouillez les bâtiments (E devant une porte).</p>
      ) : (
        <ul className="max-h-[50vh] overflow-y-auto py-1">
          {inventory.slots.map((slot) => {
            const equipped = slot.slot === inventory.equipped;
            const label = actionLabel(slot, equipped);
            return (
              <li
                key={slot.slot}
                className={`flex items-center gap-2 px-3 py-0.5 ${equipped ? 'bg-verdigris-700/30' : ''}`}
                data-testid={`slot-${slot.item}`}
              >
                <span className="w-5 text-ash tabular-nums">{slot.slot < 9 ? slot.slot + 1 : ''}</span>
                <span className="flex-1 truncate text-bone">
                  {slot.name}
                  {slot.qty > 1 && <span className="text-ash"> × {slot.qty}</span>}
                  {slot.kind === 'firearm' && <span className="text-amber"> [{slot.loaded}]</span>}
                  {(slot.kind === 'melee' || slot.kind === 'firearm') && (
                    <span className={slot.durability < 0.25 ? 'text-rust-400' : 'text-ash'}>
                      {' '}
                      {Math.round(slot.durability * 100)} %
                    </span>
                  )}
                </span>
                <span className="hidden text-sm text-ash sm:inline">{KIND_LABELS[slot.kind]}</span>
                {label && (
                  <button
                    type="button"
                    className="border border-verdigris-500 px-1.5 text-sm text-verdigris-300 hover:text-bone"
                    onClick={() => onUse(slot.slot)}
                  >
                    {label}
                  </button>
                )}
                <button
                  type="button"
                  className="border border-charcoal-600 px-1.5 text-sm text-ash hover:text-rust-400"
                  onClick={() => onDrop(slot.slot)}
                >
                  Jeter
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
