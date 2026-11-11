// Validation côté client des identifiants (mêmes contraintes que le serveur).

export type AuthMode = 'login' | 'register';

// Mêmes contraintes que server/app/api/schemas.py.
const USERNAME_PATTERN = /^[A-Za-z0-9_-]{3,24}$/;
export const PASSWORD_MIN = 8;
export const PASSWORD_MAX = 128;

export function validateCredentials(
  mode: AuthMode,
  username: string,
  password: string,
  confirm: string,
): string | null {
  if (mode === 'login') {
    return username && password ? null : 'Pseudo et mot de passe requis.';
  }
  if (!USERNAME_PATTERN.test(username)) {
    return 'Pseudo : 3 à 24 caractères (lettres, chiffres, _ ou -).';
  }
  if (password.length < PASSWORD_MIN || password.length > PASSWORD_MAX) {
    return `Mot de passe : ${PASSWORD_MIN} à ${PASSWORD_MAX} caractères.`;
  }
  if (password !== confirm) return 'Les mots de passe ne correspondent pas.';
  return null;
}
