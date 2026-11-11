import { createEventBus } from './eventBus';
import type { BridgeEvents } from './events';

export { createEventBus, type EventBus } from './eventBus';
export type { BridgeEvents, NetLinkState, NetStatusView } from './events';

/** Bus unique de l'application, partagé par React et Phaser. */
export const gameBus = createEventBus<BridgeEvents>();
