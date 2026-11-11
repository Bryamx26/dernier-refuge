// Point de montage React du jeu Phaser. Phaser est chargé à la demande (chunk séparé)
// et l'instance est détruite au démontage (compatible avec le double montage de StrictMode).
import { useEffect, useRef } from 'react';
import type Phaser from 'phaser';

export function PhaserGame({ className = '' }: { readonly className?: string }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    let game: Phaser.Game | null = null;
    let disposed = false;

    void import('./createGame').then(({ createGame }) => {
      if (!disposed) game = createGame(container);
    });

    return () => {
      disposed = true;
      game?.destroy(true);
      game = null;
    };
  }, []);

  return (
    <div
      ref={containerRef}
      className={`h-full w-full overflow-hidden ${className}`}
      data-testid="phaser-root"
    />
  );
}
