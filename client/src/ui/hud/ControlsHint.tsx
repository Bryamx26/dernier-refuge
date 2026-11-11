// Rappel discret des commandes, en bas de l'écran de jeu.
function Key({ children }: { readonly children: string }) {
  return (
    <kbd className="border border-charcoal-600 bg-charcoal-900 px-1.5 font-terminal text-base leading-none text-bone">
      {children}
    </kbd>
  );
}

export function ControlsHint() {
  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-3 flex justify-center">
      <p
        className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 text-base text-ash"
        style={{ textShadow: '2px 2px 0 #000' }}
      >
        <span className="flex items-center gap-1">
          <Key>Z</Key>
          <Key>Q</Key>
          <Key>S</Key>
          <Key>D</Key>
          <span className="ml-1">ou flèches : marcher</span>
        </span>
        <span className="flex items-center gap-1">
          <Key>Maj</Key>
          <span className="ml-1">courir</span>
        </span>
        <span>Souris : regarder</span>
      </p>
    </div>
  );
}
