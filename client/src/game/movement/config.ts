// Constantes de déplacement partagées avec le serveur (shared/movement/movement.json, alias `@shared`).
import movement from '@shared/movement/movement.json';
import type { MovementConfig } from './step';

export interface SharedMovementConfig extends MovementConfig {
  readonly max_inputs_per_tick: number;
  readonly interest_radius: number;
}

export const MOVEMENT: SharedMovementConfig = {
  walk_speed: movement.walk_speed,
  sprint_speed: movement.sprint_speed,
  player_half_size: movement.player_half_size,
  max_inputs_per_tick: movement.max_inputs_per_tick,
  interest_radius: movement.interest_radius,
};
