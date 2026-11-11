import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../api';
import { useSessionStore } from '../../state/sessionStore';
import { AuthScreen } from './AuthScreen';

function makeApi() {
  return {
    login: vi.fn(() => Promise.resolve({ access_token: 'jwt', token_type: 'bearer', expires_in: 3600 })),
    register: vi.fn(() => Promise.resolve({ id: 'u1', username: 'rodeur' })),
  };
}

describe('AuthScreen', () => {
  beforeEach(() => {
    useSessionStore.setState({ token: null, account: null });
  });

  it('affiche le titre du jeu et le formulaire de connexion', () => {
    render(<AuthScreen api={makeApi()} />);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Dernier Refuge');
    expect(screen.getByLabelText('Pseudo')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Se connecter' })).toBeInTheDocument();
  });

  it('connexion réussie : stocke le jeton', async () => {
    const api = makeApi();
    render(<AuthScreen api={api} />);
    fireEvent.change(screen.getByLabelText('Pseudo'), { target: { value: 'rodeur' } });
    fireEvent.change(screen.getByLabelText('Mot de passe'), { target: { value: 'motdepasse' } });
    fireEvent.click(screen.getByRole('button', { name: 'Se connecter' }));
    await waitFor(() => expect(useSessionStore.getState().token).toBe('jwt'));
    expect(api.login).toHaveBeenCalledWith({ username: 'rodeur', password: 'motdepasse' });
    expect(sessionStorage.getItem('dernier-refuge.session')).toContain('jwt');
  });

  it('identifiants refusés : message en français', async () => {
    const api = makeApi();
    api.login.mockRejectedValueOnce(new ApiError('http', 401, 'Identifiants invalides'));
    render(<AuthScreen api={api} />);
    fireEvent.change(screen.getByLabelText('Pseudo'), { target: { value: 'rodeur' } });
    fireEvent.change(screen.getByLabelText('Mot de passe'), { target: { value: 'mauvais' } });
    fireEvent.click(screen.getByRole('button', { name: 'Se connecter' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Identifiants invalides.');
    expect(useSessionStore.getState().token).toBeNull();
  });

  it('inscription : valide côté client avant tout appel', () => {
    const api = makeApi();
    render(<AuthScreen api={api} />);
    fireEvent.click(screen.getByRole('tab', { name: 'Inscription' }));
    fireEvent.change(screen.getByLabelText('Pseudo'), { target: { value: 'rodeur' } });
    fireEvent.change(screen.getByLabelText('Mot de passe'), { target: { value: 'court' } });
    fireEvent.click(screen.getByRole('button', { name: "S'inscrire" }));
    expect(screen.getByRole('alert')).toHaveTextContent('Mot de passe');
    expect(api.register).not.toHaveBeenCalled();
  });

  it('inscription réussie : enchaîne sur la connexion', async () => {
    const api = makeApi();
    render(<AuthScreen api={api} />);
    fireEvent.click(screen.getByRole('tab', { name: 'Inscription' }));
    fireEvent.change(screen.getByLabelText('Pseudo'), { target: { value: 'rodeur' } });
    fireEvent.change(screen.getByLabelText('Mot de passe'), { target: { value: 'motdepasse' } });
    fireEvent.change(screen.getByLabelText('Confirmation'), { target: { value: 'motdepasse' } });
    fireEvent.click(screen.getByRole('button', { name: "S'inscrire" }));
    await waitFor(() => expect(useSessionStore.getState().token).toBe('jwt'));
    expect(api.register).toHaveBeenCalledOnce();
  });
});
