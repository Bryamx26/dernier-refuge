// Types des réponses REST, alignés sur server/app/api/schemas.py (UUID sérialisés en chaînes).

export interface AccountOut {
  readonly id: string;
  readonly username: string;
}

export interface TokenOut {
  readonly access_token: string;
  readonly token_type: string;
  /** Durée de validité en secondes. */
  readonly expires_in: number;
}

export interface CharacterOut {
  readonly id: string;
  readonly name: string;
  readonly zone_id: string;
  readonly x: number;
  readonly y: number;
  readonly is_dead: boolean;
}

export interface ZoneOut {
  readonly id: string;
  readonly name: string;
  readonly max_players: number;
  readonly online: number;
  readonly is_pvp: boolean;
}

export interface JoinZoneOut {
  /** Ticket à usage unique, à passer en paramètre `ticket` du WebSocket. */
  readonly ticket: string;
  readonly ws_path: string;
  readonly expires_in: number;
}

export interface Credentials {
  readonly username: string;
  readonly password: string;
}
