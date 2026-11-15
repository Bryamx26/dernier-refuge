import { describe, expect, it } from 'vitest';
import { decodeServerMessage, isServerMessageType, parseServerMessage } from './decode';

const welcome = {
  t: 'welcome',
  seq: 1,
  tick: 10,
  d: {
    protocol_version: 2,
    zone_id: 'valcendre',
    character_id: 'abc',
    tick_rate: 20,
    server_time: 1234.5,
    entity_id: 'e-abc',
    map_id: 'valcendre',
  },
};

const entity = {
  id: 'e-abc',
  kind: 'player',
  name: 'Élise',
  x: 10.5,
  y: 4.25,
  aim: 1.2,
  anim: 'walk',
  health: 0.75,
};
const snapshot = { t: 'snapshot', seq: 4, tick: 11, d: { ack_seq: 7, entities: [entity] } };

describe('isServerMessageType', () => {
  it('accepte uniquement les types de SERVER_MESSAGE_TYPES', () => {
    expect(isServerMessageType('welcome')).toBe(true);
    expect(isServerMessageType('pong')).toBe(true);
    expect(isServerMessageType('error')).toBe(true);
    expect(isServerMessageType('ping')).toBe(false);
    expect(isServerMessageType('snapshot')).toBe(true);
    expect(isServerMessageType('input')).toBe(false);
    expect(isServerMessageType(42)).toBe(false);
  });
});

describe('decodeServerMessage', () => {
  it('décode un welcome valide', () => {
    const message = decodeServerMessage(JSON.stringify(welcome));
    expect(message).toEqual(welcome);
    if (message?.t === 'welcome') {
      // Le rétrécissement sur `t` donne accès aux champs typés.
      expect(message.d.tick_rate).toBe(20);
    }
  });

  it('décode un snapshot valide', () => {
    expect(decodeServerMessage(JSON.stringify(snapshot))).toEqual(snapshot);
  });

  it('décode pong et error', () => {
    expect(
      decodeServerMessage('{"t":"pong","seq":2,"tick":3,"d":{"client_time":5,"server_time":9}}')?.t,
    ).toBe('pong');
    expect(
      decodeServerMessage('{"t":"error","seq":3,"tick":3,"d":{"code":"rate_limited","message":"doucement"}}')
        ?.t,
    ).toBe('error');
  });

  it('décode vitals, inventory, fx et notice (phase 3)', () => {
    const vitals = {
      t: 'vitals',
      seq: 5,
      tick: 9,
      d: {
        health: 72.5,
        max_health: 100,
        hunger: 80,
        thirst: 61.2,
        bleeding: true,
        dead: false,
        action: 'Fouille : Pharmacie',
        action_progress: 0.4,
      },
    };
    expect(parseServerMessage(vitals)).toEqual(vitals);
    const slot = {
      slot: 2,
      item: 'pistol',
      name: 'Pistolet 9 mm',
      kind: 'firearm',
      qty: 1,
      weight: 0.9,
      durability: 0.5,
      loaded: 7,
    };
    const inventory = {
      t: 'inventory',
      seq: 6,
      tick: 9,
      d: { slots: [slot], capacity: 20, equipped: 2, weight: 0.9, max_weight: 18 },
    };
    expect(parseServerMessage(inventory)).toEqual(inventory);
    expect(
      parseServerMessage({ ...inventory, d: { ...inventory.d, slots: [{ ...slot, kind: 'laser' }] } }),
    ).toBeNull();
    const fx = { t: 'fx', seq: 7, tick: 9, d: { events: [{ kind: 'shot', x: 1, y: 2, x2: 9, y2: 2 }] } };
    expect(parseServerMessage(fx)).toEqual(fx);
    expect(
      parseServerMessage({ ...fx, d: { events: [{ kind: 'nuke', x: 1, y: 2, x2: 9, y2: 2 }] } }),
    ).toBeNull();
    expect(parseServerMessage({ t: 'notice', seq: 8, tick: 9, d: { text: 'Ramassé : Bandage' } })?.t).toBe(
      'notice',
    );
    expect(parseServerMessage({ t: 'notice', seq: 8, tick: 9, d: { text: '' } })).toBeNull();
  });

  it('accepte zombies et objets, refuse une santé hors de [0, 1]', () => {
    const zombie = { ...entity, id: 'z3', kind: 'zombie', name: 'Rôdeur', anim: 'attack', health: 0.4 };
    const ok = { ...snapshot, d: { ack_seq: 1, entities: [zombie] } };
    expect(parseServerMessage(ok)).toEqual(ok);
    expect(
      parseServerMessage({ ...snapshot, d: { ack_seq: 1, entities: [{ ...zombie, health: 1.5 }] } }),
    ).toBeNull();
  });

  it.each([
    ['JSON invalide', '{pas du json'],
    ['trame binaire', new ArrayBuffer(4)],
    ['tableau', '[]'],
    ['type inconnu', '{"t":"teleport","seq":1,"tick":1,"d":{}}'],
    ['snapshot vide', '{"t":"snapshot","seq":1,"tick":1,"d":{}}'],
    ['snapshot ack négatif', JSON.stringify({ ...snapshot, d: { ...snapshot.d, ack_seq: -1 } })],
    [
      'snapshot entité invalide',
      JSON.stringify({ ...snapshot, d: { ack_seq: 1, entities: [{ ...entity, anim: 'fly' }] } }),
    ],
    [
      'snapshot x non numérique',
      JSON.stringify({ ...snapshot, d: { ack_seq: 1, entities: [{ ...entity, x: '1' }] } }),
    ],
    ['welcome sans entity_id', JSON.stringify({ ...welcome, d: { ...welcome.d, entity_id: undefined } })],
    ['type client', '{"t":"ping","seq":1,"tick":1,"d":{"client_time":1}}'],
    ['seq manquant', '{"t":"pong","tick":1,"d":{"client_time":1,"server_time":1}}'],
    ['tick négatif', '{"t":"pong","seq":1,"tick":-1,"d":{"client_time":1,"server_time":1}}'],
    ['d absent', '{"t":"pong","seq":1,"tick":1}'],
    ['pong incomplet', '{"t":"pong","seq":1,"tick":1,"d":{"client_time":1}}'],
    ['code erreur inconnu', '{"t":"error","seq":1,"tick":1,"d":{"code":"boom","message":"x"}}'],
    ['welcome tick_rate nul', JSON.stringify({ ...welcome, d: { ...welcome.d, tick_rate: 0 } })],
  ])('rejette : %s', (_label, raw) => {
    expect(decodeServerMessage(raw)).toBeNull();
  });

  it('ignore les champs supplémentaires de premier niveau', () => {
    expect(parseServerMessage({ ...welcome, extra: true })).toEqual(welcome);
  });
});
