import { afterEach, describe, expect, it } from 'vitest';
import { ZoneSocket } from '../net/ZoneSocket';
import { FakeWebSocket } from '../test/FakeWebSocket';
import { toNetStatusView } from './netView';
import { setZoneSocketFactory, useZoneStore } from './zoneStore';

describe('zoneStore', () => {
  afterEach(() => {
    useZoneStore.getState().leave();
  });

  it('suit l’état du socket et projette la vue réseau', () => {
    let fake: FakeWebSocket | null = null;
    setZoneSocketFactory(
      (options) =>
        new ZoneSocket({
          ...options,
          origin: 'ws://jeu.test',
          createSocket: (url) => (fake = new FakeWebSocket(url)),
        }),
    );
    useZoneStore.getState().connect({
      zoneId: 'valcendre',
      zoneName: 'Valcendre',
      characterName: 'Élise',
      ticket: 't',
      wsPath: '/ws/zone/valcendre',
    });
    expect(useZoneStore.getState().status?.state).toBe('connecting');
    fake!.serverOpen();
    fake!.serverClose(4002);
    const { session, status } = useZoneStore.getState();
    const view = toNetStatusView(session, status);
    expect(view).toMatchObject({ state: 'closed', closeCode: 4002, zoneName: 'Valcendre' });
    expect(view.closeLabel).toMatch(/déjà connecté/);
  });
});
