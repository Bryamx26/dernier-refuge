/** Titre du jeu, en capitales pixel. */
export function GameTitle({ compact = false }: { readonly compact?: boolean }) {
  return (
    <div className={compact ? 'flex items-baseline gap-3' : 'flex flex-col items-center gap-1 text-center'}>
      <h1
        className={`font-display font-bold tracking-[0.12em] text-bone uppercase ${compact ? 'text-xl' : 'text-4xl sm:text-5xl'}`}
        style={{ textShadow: '3px 3px 0 #000, 0 0 12px rgb(95 138 118 / 0.35)' }}
      >
        Dernier Refuge
      </h1>
      {!compact && (
        <p className="text-lg tracking-widest text-ash">
          Station de survie · liaison radio <span className="blink text-verdigris-400">_</span>
        </p>
      )}
    </div>
  );
}
