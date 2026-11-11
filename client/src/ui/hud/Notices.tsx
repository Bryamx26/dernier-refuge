// Messages courts du serveur (butin, chargeur vide…), au-dessus du rappel des commandes.
import { useEffect } from 'react';
import { useGameStore } from '../../state/gameStore';

export function Notices() {
  const notices = useGameStore((s) => s.notices);
  const prune = useGameStore((s) => s.pruneNotices);
  useEffect(() => {
    const timer = setInterval(() => prune(), 500);
    return () => clearInterval(timer);
  }, [prune]);
  if (notices.length === 0) return null;
  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-12 flex flex-col items-center gap-1">
      {notices.map((n) => (
        <p
          key={n.id}
          className="bg-charcoal-950/80 px-3 text-lg text-bone"
          style={{ textShadow: '2px 2px 0 #000' }}
          data-testid="notice"
        >
          {n.text}
        </p>
      ))}
    </div>
  );
}
