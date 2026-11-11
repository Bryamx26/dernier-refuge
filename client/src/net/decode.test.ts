import { describe, expect, it } from 'vitest';
import { decodeServerMessage, isServerMessageType, parseServerMessage } from './decode';

const welcome = {
  t: 'welcome',
  seq: 1,
  tick: 10,
  d: { protocol_version: 1, zone_id: 'valcendre', character_id: 'abc', tick_rate: 20, server_time: 1234.5 },
};

describe('isServerMessageType', () => {
  it('accepte uniquement les types de SERVER_MESSAGE_TYPES', () => {
    expect(isServerMessageType('welcome')).toBe(true);
    expect(isServerMessageType('pong')).toBe(true);
    expect(isServerMessageType('error')).toBe(true);
    expect(isServerMessageType('ping')).toBe(false);
    expect(isServerMessageType('snapshot')).toBe(false);
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

  it('décode pong et error', () => {
    expect(
      decodeServerMessage('{"t":"pong","seq":2,"tick":3,"d":{"client_time":5,"server_time":9}}')?.t,
    ).toBe('pong');
    expect(
      decodeServerMessage('{"t":"error","seq":3,"tick":3,"d":{"code":"rate_limited","message":"doucement"}}')
        ?.t,
    ).toBe('error');
  });

  it.each([
    ['JSON invalide', '{pas du json'],
    ['trame binaire', new ArrayBuffer(4)],
    ['tableau', '[]'],
    ['type inconnu', '{"t":"snapshot","seq":1,"tick":1,"d":{}}'],
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
