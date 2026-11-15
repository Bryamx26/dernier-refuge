// Écran de jeu : canvas Phaser plein écran + HUD React superposé.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { gameBus, type GameStatsView } from '../../bridge';
import { PhaserGame } from '../../game/PhaserGame';
import { useGameStore } from '../../state/gameStore';
import { toNetStatusView } from '../../state/netView';
import { useZoneStore } from '../../state/zoneStore';
import { Button } from '../components/Button';
import { ControlsHint } from '../hud/ControlsHint';
import { InventoryPanel } from '../hud/InventoryPanel';
import { Notices } from '../hud/Notices';
import { ActionProgress, SurvivalPanel } from '../hud/SurvivalPanel';
import { NetPanel } from '../hud/NetPanel';
import { WorldPanel } from '../hud/WorldPanel';

export function GameScreen() {
  const session = useZoneStore((s) => s.session);
  const status = useZoneStore((s) => s.status);
  const client = useZoneStore((s) => s.client);
  const leave = useZoneStore((s) => s.leave);
  const view = useMemo(() => toNetStatusView(session, status), [session, status]);
  const [stats, setStats] = useState<GameStatsView | null>(() => gameBus.last('game:stats') ?? null);
  const vitals = useGameStore((s) => s.vitals);
  const inventory = useGameStore((s) => s.inventory);
  const [inventoryOpen, setInventoryOpen] = useState(false);
  const use = useCallback((slot: number) => client?.sendAction('use', slot), [client]);
  const drop = useCallback((slot: number) => client?.sendAction('drop', slot), [client]);

  // I ou Tab : ouvrir / fermer l'inventaire ; Échap : le fermer.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.repeat || event.ctrlKey || event.metaKey || event.altKey) return;
      if (event.code === 'KeyI' || event.code === 'Tab') {
        event.preventDefault();
        setInventoryOpen((open) => !open);
      } else if (event.code === 'Escape') {
        setInventoryOpen(false);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

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
          <SurvivalPanel vitals={vitals} inventory={inventory} />
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
          <Button variant="ghost" onClick={() => setInventoryOpen((open) => !open)}>
            Inventaire (I)
          </Button>
          {inventoryOpen && (
            <InventoryPanel
              inventory={inventory}
              onUse={use}
              onDrop={drop}
              onClose={() => setInventoryOpen(false)}
            />
          )}
        </div>
      </div>
      <ActionProgress vitals={vitals} />
      {vitals?.dead && (
        <div className="pointer-events-auto absolute inset-0 flex flex-col items-center justify-center gap-4 bg-charcoal-950/70">
          <p className="font-display text-3xl tracking-[0.2em] text-rust-400 uppercase" data-testid="dead">
            Vous êtes mort
          </p>
          <p className="text-lg text-ash">Vos affaires sont restées là où vous êtes tombé.</p>
          <Button onClick={() => client?.sendAction('respawn')}>Réapparaître</Button>
        </div>
      )}
      <Notices />
      <ControlsHint />
    </main>
  );
}
