// Écran de jeu : canvas Phaser plein écran + HUD React superposé.
import { useEffect, useMemo, useState } from 'react';
import { gameBus, type GameStatsView } from '../../bridge';
import { PhaserGame } from '../../game/PhaserGame';
import { toNetStatusView } from '../../state/netView';
import { useZoneStore } from '../../state/zoneStore';
import { Button } from '../components/Button';
import { ControlsHint } from '../hud/ControlsHint';
import { NetPanel } from '../hud/NetPanel';
import { WorldPanel } from '../hud/WorldPanel';

export function GameScreen() {
  const session = useZoneStore((s) => s.session);
  const status = useZoneStore((s) => s.status);
  const client = useZoneStore((s) => s.client);
  const leave = useZoneStore((s) => s.leave);
  const view = useMemo(() => toNetStatusView(session, status), [session, status]);
  const [stats, setStats] = useState<GameStatsView | null>(() => gameBus.last('game:stats') ?? null);

  // React → Phaser : état réseau (affiché par la WorldScene) et liaison de jeu à piloter.
  useEffect(() => {
    gameBus.emit('net:status', view);
  }, [view]);

  useEffect(() => {
    gameBus.emit('zone:link', client);
    return () => gameBus.emit('zone:link', null);
  }, [client]);

  // Phaser → React : mesures du monde pour le HUD (quelques fois par seconde).
  useEffect(() => gameBus.on('game:stats', setStats), []);

  return (
    <main className="relative h-full w-full overflow-hidden bg-charcoal-950">
      <PhaserGame className="absolute inset-0" />
      <div className="pointer-events-none absolute inset-0 flex items-start justify-between gap-4 p-3">
        <div className="flex flex-col gap-3">
          <NetPanel view={view} />
          <WorldPanel stats={stats} />
        </div>
        <div className="pointer-events-auto flex flex-col items-end gap-2">
          {session && (
            <span className="text-ash" style={{ textShadow: '2px 2px 0 #000' }}>
              Survivant : <span className="text-bone">{session.characterName}</span>
            </span>
          )}
          <Button variant={view.state === 'closed' ? 'primary' : 'danger'} onClick={leave}>
            {view.state === 'closed' ? 'Retour' : 'Quitter la zone'}
          </Button>
        </div>
      </div>
      <ControlsHint />
    </main>
  );
}
