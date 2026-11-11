// Projection de l'état de connexion vers la vue partagée avec Phaser.
import type { NetStatusView } from '../bridge';
import { describeCloseCode } from '../net/closeCodes';
import type { ZoneSession } from './zoneStore';
import type { ZoneSocketStatus } from '../net/ZoneSocket';

export function toNetStatusView(session: ZoneSession | null, status: ZoneSocketStatus | null): NetStatusView {
  return {
    state: status?.state ?? 'idle',
    zoneId: session?.zoneId ?? null,
    zoneName: session?.zoneName ?? null,
    rttMs: status?.rttMs ?? null,
    serverTick: status?.serverTick ?? null,
    tickRate: status?.welcome?.tick_rate ?? null,
    closeCode: status?.closeCode ?? null,
    closeLabel: status?.state === 'closed' ? describeCloseCode(status.closeCode) : '',
  };
}
