import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { FakeWebSocket } from '../test/FakeWebSocket';
import { describeCloseCode } from './closeCodes';
import { ZoneSocket, type ZoneSocketStatus } from './ZoneSocket';

function setup(options: { pingIntervalMs?: number } = {}) {
  let clock = 1000;
  let fake: FakeWebSocket | null = null;
  const socket = new ZoneSocket({
    zoneId: 'valcendre',
    ticket: 'tkt/+=',
    origin: 'ws://jeu.test',
    createSocket: (url) => (fake = new FakeWebSocket(url)),
    now: () => clock,
    pingIntervalMs: options.pingIntervalMs ?? 1000,
  });
  const statuses: ZoneSocketStatus[] = [];
  socket.onStatus((s) => statuses.push(s));
  socket.connect();
  return {
    socket,
    statuses,
    get ws(): FakeWebSocket {
      if (!fake) throw new Error('pas de socket');
      return fake;
    },
    setClock: (t: number) => {
      clock = t;
    },
  };
}

const welcome = {
  t: 'welcome',
  seq: 1,
  tick: 42,
  d: { protocol_version: 1, zone_id: 'valcendre', character_id: 'c1', tick_rate: 20, server_time: 99 },
};

describe('ZoneSocket', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('construit l’URL /ws/zone/{zone}?ticket=… et passe par connecting → open', () => {
    const { ws, socket, statuses } = setup();
    expect(ws.url).toBe('ws://jeu.test/ws/zone/valcendre?ticket=tkt%2F%2B%3D');
    expect(socket.getStatus().state).toBe('connecting');
    ws.serverOpen();
    expect(socket.getStatus().state).toBe('open');
    expect(statuses.map((s) => s.state)).toEqual(['idle', 'connecting', 'open']);
  });

  it('expose welcome et le tick serveur, et notifie les abonnés typés', () => {
    const { ws, socket } = setup();
    const onWelcome = vi.fn();
    socket.on('welcome', (message) => {
      onWelcome(message.d.tick_rate);
    });
    ws.serverOpen();
    ws.serverSend(welcome);
    expect(onWelcome).toHaveBeenCalledWith(20);
    expect(socket.getStatus().welcome?.zone_id).toBe('valcendre');
    expect(socket.getStatus().serverTick).toBe(42);
  });

  it('envoie un ping à l’ouverture puis chaque seconde, avec seq croissant', () => {
    const { ws, setClock } = setup();
    ws.serverOpen();
    setClock(2000);
    vi.advanceTimersByTime(1000);
    setClock(3000);
    vi.advanceTimersByTime(1000);
    expect(ws.sentMessages()).toEqual([
      { t: 'ping', seq: 1, d: { client_time: 1000 } },
      { t: 'ping', seq: 2, d: { client_time: 2000 } },
      { t: 'ping', seq: 3, d: { client_time: 3000 } },
    ]);
  });

  it('calcule un RTT lissé à partir des pong', () => {
    const { ws, socket, setClock } = setup();
    ws.serverOpen();
    setClock(1100);
    ws.serverSend({ t: 'pong', seq: 2, tick: 43, d: { client_time: 1000, server_time: 5 } });
    expect(socket.getStatus().rttMs).toBe(100);
    setClock(2200);
    ws.serverSend({ t: 'pong', seq: 3, tick: 44, d: { client_time: 2000, server_time: 6 } });
    // 100 + 0,2 × (200 − 100)
    expect(socket.getStatus().rttMs).toBeCloseTo(120);
    expect(socket.getStatus().serverTick).toBe(44);
  });

  it('ignore les messages inconnus ou invalides sans fermer la liaison', () => {
    const { ws, socket } = setup();
    const onAny = vi.fn();
    socket.on('welcome', onAny);
    socket.on('pong', onAny);
    socket.on('error', onAny);
    ws.serverOpen();
    ws.serverSend({ t: 'snapshot', seq: 9, tick: 1, d: {} });
    ws.serverSend('pas du json');
    expect(onAny).not.toHaveBeenCalled();
    expect(socket.ignoredFrames).toBe(2);
    expect(socket.getStatus().state).toBe('open');
  });

  it('expose le code de fermeture 4001 et arrête les pings', () => {
    const { ws, socket } = setup();
    ws.serverOpen();
    ws.serverClose(4001, 'ticket invalide');
    const status = socket.getStatus();
    expect(status.state).toBe('closed');
    expect(status.closeCode).toBe(4001);
    expect(status.closeReason).toBe('ticket invalide');
    expect(describeCloseCode(status.closeCode)).toMatch(/Ticket/);
    const sentBefore = ws.sent.length;
    vi.advanceTimersByTime(5000);
    expect(ws.sent.length).toBe(sentBefore);
    expect(socket.send('ping', { client_time: 1 })).toBe(false);
  });

  it('se désabonne proprement', () => {
    const { ws, socket } = setup();
    const handler = vi.fn();
    const off = socket.on('pong', handler);
    off();
    ws.serverOpen();
    ws.serverSend({ t: 'pong', seq: 2, tick: 1, d: { client_time: 1000, server_time: 1 } });
    expect(handler).not.toHaveBeenCalled();
  });

  it('ferme côté client avec le code 1000', () => {
    const { ws, socket } = setup();
    ws.serverOpen();
    socket.close();
    expect(ws.closedWith?.code).toBe(1000);
    expect(socket.getStatus()).toMatchObject({ state: 'closed', closeCode: 1000 });
  });

  it('refuse une seconde connexion (ticket à usage unique)', () => {
    const { socket } = setup();
    expect(() => socket.connect()).toThrow();
  });
});
