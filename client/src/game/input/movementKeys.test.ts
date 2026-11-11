import { describe, expect, it } from 'vitest';
import { MovementKeys } from './movementKeys';

const key = (code: string, k = '') => ({ code, key: k });

describe('MovementKeys', () => {
  it('ZQSD sur AZERTY : les positions physiques KeyW/KeyA/KeyS/KeyD', () => {
    const keys = new MovementKeys();
    keys.keyDown(key('KeyW', 'z'));
    keys.keyDown(key('KeyA', 'q'));
    expect(keys.axes()).toEqual({ moveX: -1, moveY: -1, sprint: false });
    keys.keyUp(key('KeyW', 'z'));
    expect(keys.axes()).toEqual({ moveX: -1, moveY: 0, sprint: false });
  });

  it('WASD sur QWERTY, flèches et Maj pour sprinter', () => {
    const keys = new MovementKeys();
    keys.keyDown(key('KeyD', 'd'));
    keys.keyDown(key('ArrowDown', 'ArrowDown'));
    keys.keyDown(key('ShiftLeft', 'Shift'));
    expect(keys.axes()).toEqual({ moveX: 1, moveY: 1, sprint: true });
    keys.keyUp(key('ShiftLeft', 'Shift'));
    expect(keys.axes().sprint).toBe(false);
  });

  it('directions opposées : annulation ; touche logique Z reconnue', () => {
    const keys = new MovementKeys();
    keys.keyDown(key('ArrowLeft'));
    keys.keyDown(key('ArrowRight'));
    expect(keys.axes().moveX).toBe(0);
    keys.reset();
    expect(keys.keyDown(key('KeyZ', 'z'))).toBe(true);
    expect(keys.axes().moveY).toBe(-1);
  });

  it('ignore les raccourcis et les touches hors jeu', () => {
    const keys = new MovementKeys();
    expect(keys.keyDown({ code: 'KeyW', key: 'w', ctrlKey: true })).toBe(false);
    expect(keys.keyDown(key('KeyE', 'e'))).toBe(false);
    expect(keys.axes()).toEqual({ moveX: 0, moveY: 0, sprint: false });
  });
});
