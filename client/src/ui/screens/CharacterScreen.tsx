// Écran des survivants : liste, création et entrée dans une zone.
import { useEffect, useState, type FormEvent } from 'react';
import { describeApiError, type ApiClient, type CharacterOut, type ZoneOut } from '../../api';
import { api as defaultApi } from '../../api/instance';
import { useSessionStore } from '../../state/sessionStore';
import { useZoneStore } from '../../state/zoneStore';
import { Alert } from '../components/Alert';
import { Button } from '../components/Button';
import { Frame } from '../components/Frame';
import { GameTitle } from '../components/GameTitle';
import { TextField } from '../components/TextField';

// Même contrainte que server/app/api/schemas.py (CHARACTER_NAME_PATTERN).
const CHARACTER_NAME_PATTERN = /^[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ' -]{1,22}[A-Za-zÀ-ÿ]$/;

interface CharacterScreenProps {
  readonly api?: Pick<ApiClient, 'listCharacters' | 'createCharacter' | 'listZones' | 'joinZone'>;
}

export function CharacterScreen({ api = defaultApi }: CharacterScreenProps) {
  const account = useSessionStore((s) => s.account);
  const logout = useSessionStore((s) => s.logout);
  const connect = useZoneStore((s) => s.connect);

  const [characters, setCharacters] = useState<CharacterOut[]>([]);
  const [zones, setZones] = useState<ZoneOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [createError, setCreateError] = useState<string | null>(null);
  const [joinError, setJoinError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.listCharacters(), api.listZones()])
      .then(([chars, zoneList]) => {
        if (cancelled) return;
        setCharacters(chars);
        setZones(zoneList);
        setLoadError(null);
      })
      .catch((err: unknown) => {
        if (!cancelled) setLoadError(describeApiError(err, 'characters'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [api, reloadKey]);

  const reload = () => {
    setLoading(true);
    setReloadKey((k) => k + 1);
  };

  const zoneName = (zoneId: string) => zones.find((z) => z.id === zoneId)?.name ?? zoneId;

  const handleCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (!CHARACTER_NAME_PATTERN.test(trimmed)) {
      setCreateError('Nom : 3 à 24 lettres (espaces, apostrophes et tirets autorisés au milieu).');
      return;
    }
    setBusy(true);
    setCreateError(null);
    try {
      const created = await api.createCharacter(trimmed);
      setCharacters((list) => [...list, created]);
      setName('');
    } catch (err) {
      setCreateError(describeApiError(err, 'createCharacter'));
    } finally {
      setBusy(false);
    }
  };

  const handleJoin = async (character: CharacterOut) => {
    setBusy(true);
    setJoinError(null);
    try {
      const join = await api.joinZone(character.zone_id, character.id);
      connect({
        zoneId: character.zone_id,
        zoneName: zoneName(character.zone_id),
        characterName: character.name,
        ticket: join.ticket,
        wsPath: join.ws_path,
      });
    } catch (err) {
      setJoinError(describeApiError(err, 'join'));
      setBusy(false);
    }
  };

  return (
    <main className="mx-auto flex min-h-full w-full max-w-4xl flex-col gap-6 px-4 py-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <GameTitle compact />
        <div className="flex items-center gap-3 text-ash">
          <span>
            Opérateur : <span className="text-bone">{account?.username ?? '—'}</span>
          </span>
          <Button variant="ghost" onClick={logout}>
            Déconnexion
          </Button>
        </div>
      </header>

      {loadError && (
        <div className="flex flex-col items-start gap-2">
          <Alert>{loadError}</Alert>
          <Button variant="ghost" onClick={reload}>
            Réessayer
          </Button>
        </div>
      )}

      <div className="grid gap-6 md:grid-cols-[3fr_2fr]">
        <Frame
          title="Survivants"
          tag={loading ? 'LECTURE…' : `${characters.length} ${characters.length > 1 ? 'FICHES' : 'FICHE'}`}
        >
          {!loading && characters.length === 0 && (
            <p className="text-ash">Aucun survivant enregistré. Créez-en un pour rejoindre une zone.</p>
          )}
          <ul className="flex flex-col gap-2">
            {characters.map((character) => (
              <li
                key={character.id}
                className="flex items-center justify-between gap-3 border-2 border-charcoal-700 bg-charcoal-950/60 px-3 py-2"
              >
                <div>
                  <p className="font-display text-lg text-bone">{character.name}</p>
                  <p className="text-base text-ash">
                    Zone : {zoneName(character.zone_id)} · position {Math.round(character.x)},{' '}
                    {Math.round(character.y)}
                  </p>
                </div>
                <Button disabled={busy || character.is_dead} onClick={() => void handleJoin(character)}>
                  Rejoindre
                </Button>
              </li>
            ))}
          </ul>
          {joinError && (
            <div className="mt-3">
              <Alert>{joinError}</Alert>
            </div>
          )}
        </Frame>

        <div className="flex flex-col gap-6">
          <Frame title="Nouveau survivant">
            <form className="flex flex-col gap-3" onSubmit={(e) => void handleCreate(e)} noValidate>
              <TextField
                label="Nom"
                name="character-name"
                value={name}
                maxLength={24}
                onChange={(e) => setName(e.target.value)}
                hint="3 à 24 lettres"
              />
              {createError && <Alert>{createError}</Alert>}
              <Button type="submit" disabled={busy}>
                Créer
              </Button>
            </form>
          </Frame>

          <Frame
            title="Zones"
            tag={
              <button className="hover:text-bone" onClick={reload}>
                ↻
              </button>
            }
          >
            <ul className="flex flex-col gap-1">
              {zones.map((zone) => (
                <li key={zone.id} className="flex justify-between gap-2">
                  <span className="text-bone">
                    {zone.name}
                    {zone.is_pvp && <span className="ml-2 text-rust-400">[JcJ]</span>}
                  </span>
                  <span className="text-ash">
                    {zone.online}/{zone.max_players}
                  </span>
                </li>
              ))}
              {!loading && zones.length === 0 && <li className="text-ash">Aucune zone disponible.</li>}
            </ul>
          </Frame>
        </div>
      </div>
    </main>
  );
}
