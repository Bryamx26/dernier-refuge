import { beforeEach, describe, expect, it } from 'vitest';
import { MAX_NOTICES, NOTICE_TTL_MS, useGameStore } from './gameStore';

describe('gameStore', () => {
  beforeEach(() => useGameStore.getState().reset());

  it('garde les derniers messages et retire les expirés', () => {
    const store = useGameStore.getState();
    for (let i = 0; i < MAX_NOTICES + 2; i += 1) store.pushNotice(`message ${i}`, 1000 + i);
    let notices = useGameStore.getState().notices;
    expect(notices).toHaveLength(MAX_NOTICES);
    expect(notices[0]!.text).toBe('message 2');
    useGameStore.getState().pruneNotices(1000 + 3 + NOTICE_TTL_MS);
    notices = useGameStore.getState().notices;
    expect(notices.map((n) => n.text)).toEqual(['message 4', 'message 5']);
  });
});
