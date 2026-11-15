// Rappel discret des commandes, en bas de l'écran de jeu.
function Key({ children }: { readonly children: string }) {
  return (
    <kbd className="border border-charcoal-600 bg-charcoal-900 px-1.5 font-terminal text-base leading-none text-bone">
      {children}
    </kbd>
  );
}

function Hint({ keys, label }: { readonly keys: readonly string[]; readonly label: string }) {
  return (
    <span className="flex items-center gap-1">
      {keys.map((k) => (
        <Key key={k}>{k}</Key>
      ))}
      <span className="ml-1">{label}</span>
    </span>
  );
}

export function ControlsHint() {
  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-3 flex justify-center">
      <p
        className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1 px-3 text-base text-ash"
        style={{ textShadow: '2px 2px 0 #000' }}
      >
        <Hint keys={['Z', 'Q', 'S', 'D']} label="marcher" />
        <Hint keys={['Maj']} label="courir" />
        <span>Clic gauche : frapper / tirer</span>
        <Hint keys={['E']} label="fouiller, ramasser" />
        <Hint keys={['R']} label="recharger" />
        <Hint keys={['1-9']} label="utiliser" />
        <Hint keys={['I']} label="inventaire" />
      </p>
    </div>
  );
}
