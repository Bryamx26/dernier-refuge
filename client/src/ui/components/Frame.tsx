import type { ReactNode } from 'react';

interface FrameProps {
  /** Libellé de la barre de titre, affiché en capitales. */
  readonly title: string;
  readonly children: ReactNode;
  readonly className?: string;
  /** Indication à droite de la barre de titre (ex. « EN LIGNE »). */
  readonly tag?: ReactNode;
}

/** Cadre de terminal de survie : barre de titre + contenu. */
export function Frame({ title, children, className = '', tag }: FrameProps) {
  return (
    <section className={`terminal-frame ${className}`} aria-label={title}>
      <header className="flex items-center justify-between gap-4 border-b-2 border-charcoal-600 bg-charcoal-700/60 px-3 py-1">
        <h2 className="font-display text-sm tracking-[0.2em] text-verdigris-300 uppercase">{title}</h2>
        {tag !== undefined && <span className="text-sm text-ash">{tag}</span>}
      </header>
      <div className="p-4">{children}</div>
    </section>
  );
}
