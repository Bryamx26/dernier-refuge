// Écran de connexion / inscription.
import { useState, type FormEvent } from 'react';
import { describeApiError, type ApiClient } from '../../api';
import { api as defaultApi } from '../../api/instance';
import { useSessionStore } from '../../state/sessionStore';
import { Alert } from '../components/Alert';
import { Button } from '../components/Button';
import { Frame } from '../components/Frame';
import { GameTitle } from '../components/GameTitle';
import { TextField } from '../components/TextField';
import { PASSWORD_MAX, PASSWORD_MIN, validateCredentials, type AuthMode } from './authValidation';

interface AuthScreenProps {
  readonly api?: Pick<ApiClient, 'login' | 'register'>;
}

export function AuthScreen({ api = defaultApi }: AuthScreenProps) {
  const setToken = useSessionStore((s) => s.setToken);
  const [mode, setMode] = useState<AuthMode>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const switchMode = (next: AuthMode) => {
    setMode(next);
    setError(null);
    setConfirm('');
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const name = username.trim();
    const invalid = validateCredentials(mode, name, password, confirm);
    if (invalid) {
      setError(invalid);
      return;
    }
    setError(null);
    setPending(true);
    try {
      if (mode === 'register') {
        try {
          await api.register({ username: name, password });
        } catch (err) {
          setError(describeApiError(err, 'register'));
          return;
        }
      }
      const token = await api.login({ username: name, password });
      setToken(token.access_token);
    } catch (err) {
      setError(describeApiError(err, 'login'));
    } finally {
      setPending(false);
    }
  };

  return (
    <main className="flex min-h-full flex-col items-center justify-center gap-8 px-4 py-10">
      <GameTitle />
      <Frame
        title={mode === 'login' ? 'Identification' : 'Nouveau survivant'}
        tag={mode === 'login' ? 'ACCÈS' : 'ENREGISTREMENT'}
        className="w-full max-w-md"
      >
        <div role="tablist" aria-label="Mode d'accès" className="mb-4 grid grid-cols-2 gap-2">
          <Button
            role="tab"
            aria-selected={mode === 'login'}
            variant={mode === 'login' ? 'primary' : 'ghost'}
            onClick={() => switchMode('login')}
          >
            Connexion
          </Button>
          <Button
            role="tab"
            aria-selected={mode === 'register'}
            variant={mode === 'register' ? 'primary' : 'ghost'}
            onClick={() => switchMode('register')}
          >
            Inscription
          </Button>
        </div>

        <form className="flex flex-col gap-4" onSubmit={(e) => void handleSubmit(e)} noValidate>
          <TextField
            label="Pseudo"
            name="username"
            value={username}
            maxLength={24}
            autoComplete="username"
            autoFocus
            onChange={(e) => setUsername(e.target.value)}
            hint={mode === 'register' ? '3 à 24 caractères : lettres, chiffres, _ ou -' : undefined}
          />
          <TextField
            label="Mot de passe"
            name="password"
            type="password"
            value={password}
            maxLength={PASSWORD_MAX}
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            onChange={(e) => setPassword(e.target.value)}
            hint={mode === 'register' ? `${PASSWORD_MIN} caractères minimum` : undefined}
          />
          {mode === 'register' && (
            <TextField
              label="Confirmation"
              name="confirm"
              type="password"
              value={confirm}
              maxLength={PASSWORD_MAX}
              autoComplete="new-password"
              onChange={(e) => setConfirm(e.target.value)}
            />
          )}
          {error && <Alert>{error}</Alert>}
          <Button type="submit" disabled={pending} className="mt-2">
            {pending ? 'Transmission…' : mode === 'login' ? 'Se connecter' : "S'inscrire"}
          </Button>
        </form>
      </Frame>
      <p className="text-base text-ash">Prototype · phase 2</p>
    </main>
  );
}
