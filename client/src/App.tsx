// Aiguillage des écrans selon la session et la zone courante.
import { api } from './api/instance';
import { useAccountBootstrap } from './state/useAccountBootstrap';
import { useSessionStore } from './state/sessionStore';
import { useZoneStore } from './state/zoneStore';
import { Alert } from './ui/components/Alert';
import { Button } from './ui/components/Button';
import { GameTitle } from './ui/components/GameTitle';
import { AuthScreen } from './ui/screens/AuthScreen';
import { CharacterScreen } from './ui/screens/CharacterScreen';
import { GameScreen } from './ui/screens/GameScreen';

export function App() {
  const token = useSessionStore((s) => s.token);
  const account = useSessionStore((s) => s.account);
  const logout = useSessionStore((s) => s.logout);
  const inZone = useZoneStore((s) => s.session !== null);
  const { error, retry } = useAccountBootstrap(api);

  let screen;
  if (!token) {
    screen = <AuthScreen />;
  } else if (!account) {
    screen = (
      <main className="flex h-full flex-col items-center justify-center gap-6 px-4">
        <GameTitle />
        {error ? (
          <div className="flex flex-col items-center gap-3">
            <Alert>{error}</Alert>
            <div className="flex gap-2">
              <Button onClick={retry}>Réessayer</Button>
              <Button variant="ghost" onClick={logout}>
                Déconnexion
              </Button>
            </div>
          </div>
        ) : (
          <p className="text-ash">
            Vérification de l&apos;identité<span className="blink">…</span>
          </p>
        )}
      </main>
    );
  } else if (inZone) {
    screen = <GameScreen />;
  } else {
    screen = <CharacterScreen />;
  }

  return <div className="scanlines h-full">{screen}</div>;
}
