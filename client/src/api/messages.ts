// Traduction des erreurs REST en messages d'interface (français).
import { isApiError } from './errors';

export type ApiContext = 'login' | 'register' | 'characters' | 'createCharacter' | 'zones' | 'join';

const BY_STATUS: Partial<Record<ApiContext, Partial<Record<number, string>>>> = {
  login: { 401: 'Identifiants invalides.', 403: 'Ce compte est suspendu.' },
  register: { 409: 'Ce pseudo est déjà pris.' },
  createCharacter: { 409: 'Nom déjà pris ou nombre maximal de survivants atteint.' },
  join: {
    404: 'Personnage ou zone introuvable.',
    409: 'Ce survivant est mort ou se trouve dans une autre zone.',
  },
};

export function describeApiError(error: unknown, context: ApiContext): string {
  if (!isApiError(error)) return 'Erreur inattendue.';
  if (error.kind === 'network') return 'Serveur injoignable. Vérifiez la liaison.';
  if (error.kind === 'invalid_response') return 'Réponse illisible du serveur.';
  const specific = BY_STATUS[context]?.[error.status];
  if (specific) return specific;
  if (error.status === 401) return 'Session expirée. Reconnectez-vous.';
  if (error.status === 422) return 'Données refusées par le serveur.';
  if (error.status === 429) return 'Trop de tentatives. Patientez un instant.';
  if (error.status >= 500) return 'Le serveur a rencontré une erreur.';
  return `Erreur ${error.status}.`;
}
