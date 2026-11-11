// Clavier de déplacement indépendant de la disposition : on lit `event.code` (position physique).
// KeyW/KeyA/KeyS/KeyD = ZQSD sur AZERTY et WASD sur QWERTY ; on accepte aussi les touches *logiques*
// Z et Q (`event.key`) pour un AZERTY mal détecté, sans conflit avec les positions physiques.
// Aucune dépendance à Phaser : testable seul.

export type Direction = 'up' | 'down' | 'left' | 'right';

const CODE_DIRECTIONS: Readonly<Record<string, Direction>> = {
  KeyW: 'up',
  KeyA: 'left',
  KeyS: 'down',
  KeyD: 'right',
  ArrowUp: 'up',
  ArrowLeft: 'left',
  ArrowDown: 'down',
  ArrowRight: 'right',
};

const KEY_DIRECTIONS: Readonly<Record<string, Direction>> = {
  z: 'up',
  q: 'left',
};

const SPRINT_CODES = new Set(['ShiftLeft', 'ShiftRight']);

/** Sous-ensemble de KeyboardEvent utilisé ici. */
export interface KeyEventLike {
  readonly code: string;
  readonly key: string;
  readonly repeat?: boolean;
  readonly ctrlKey?: boolean;
  readonly metaKey?: boolean;
  readonly altKey?: boolean;
}

export interface MoveAxes {
  readonly moveX: number;
  readonly moveY: number;
  readonly sprint: boolean;
}

export class MovementKeys {
  /** Touche physique enfoncée → direction retenue à l'appui (relâchée à l'identique). */
  private readonly held = new Map<string, Direction>();
  private readonly sprintHeld = new Set<string>();

  /** Traite un appui ; renvoie vrai si la touche est une touche de jeu (à ne pas propager). */
  keyDown(event: KeyEventLike): boolean {
    if (event.ctrlKey || event.metaKey || event.altKey) return false;
    if (SPRINT_CODES.has(event.code)) {
      this.sprintHeld.add(event.code);
      return true;
    }
    const direction = CODE_DIRECTIONS[event.code] ?? KEY_DIRECTIONS[event.key.toLowerCase()];
    if (!direction) return false;
    this.held.set(event.code, direction);
    return true;
  }

  keyUp(event: KeyEventLike): boolean {
    if (SPRINT_CODES.has(event.code)) {
      this.sprintHeld.delete(event.code);
      return true;
    }
    return this.held.delete(event.code);
  }

  /** Relâche tout (perte de focus : sinon une touche resterait « collée »). */
  reset(): void {
    this.held.clear();
    this.sprintHeld.clear();
  }

  axes(): MoveAxes {
    const dirs = new Set(this.held.values());
    const moveX = (dirs.has('right') ? 1 : 0) - (dirs.has('left') ? 1 : 0);
    const moveY = (dirs.has('down') ? 1 : 0) - (dirs.has('up') ? 1 : 0);
    // La diagonale (1, 1) est normalisée par step() lui-même.
    return { moveX, moveY, sprint: this.sprintHeld.size > 0 };
  }
}
