// Écran de jeu : canvas Phaser plein écran + HUD React superposé.
import { useEffect, useMemo } from 'react';
import { gameBus } from '../../bridge';
import { PhaserGame } from '../../game/PhaserGame';
import { toNetStatusView } from '../../state/netView';
import { useZoneStore } from '../../state/zoneStore';
import { Button } from '../components/Button';
import { NetPanel } from '../hud/NetPanel';

export function GameScreen() {
  const session = useZoneStore((s) => s.session);
  const status = useZoneStore((s) => s.status);
  const leave = useZoneStore((s) => s.leave);
  const view = useMemo(() => toNetStatusView(session, status), [session, status]);

  // React → Phaser : la WorldScene affiche l'état réseau reçu par le bridge.
  useEffect(() => {
    gameBus.emit('net:status', view);
  }, [view]);

  return (
    <main className="relative h-full w-full overflow-hidden bg-charcoal-950">
      <PhaserGame className="absolute inset-0" />
      <div className="pointer-events-none absolute inset-0 flex items-start justify-between gap-4 p-3">
        <NetPanel view={view} />
        <div className="pointer-events-auto flex flex-col items-end gap-2">
          {session && (
            <span className="text-ash">
              Survivant : <span className="text-bone">{session.characterName}</span>
            </span>
          )}
          <Button variant={view.state === 'closed' ? 'primary' : 'danger'} onClick={leave}>
            {view.state === 'closed' ? 'Retour' : 'Quitter la zone'}
          </Button>
        </div>
      </div>
    </main>
  );
}
