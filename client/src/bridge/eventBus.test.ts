import { describe, expect, it, vi } from 'vitest';
import { createEventBus } from './eventBus';

type Events = { a: number; b: { label: string } };

describe('createEventBus', () => {
  it('émet aux abonnés, mémorise la dernière valeur et se désabonne', () => {
    const bus = createEventBus<Events>();
    const listener = vi.fn();
    const off = bus.on('a', listener);
    bus.emit('a', 1);
    off();
    bus.emit('a', 2);
    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener).toHaveBeenCalledWith(1);
    expect(bus.last('a')).toBe(2);
    expect(bus.last('b')).toBeUndefined();
  });
});
