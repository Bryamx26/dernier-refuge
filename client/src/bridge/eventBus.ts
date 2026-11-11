// Bus d'événements typé, sans dépendance à React ni à Phaser.

export type EventMap = Record<string, unknown>;
export type Listener<T> = (payload: T) => void;

export interface EventBus<E extends EventMap> {
  emit<K extends keyof E>(event: K, payload: E[K]): void;
  /** S'abonne ; renvoie la fonction de désabonnement. */
  on<K extends keyof E>(event: K, listener: Listener<E[K]>): () => void;
  /** Dernière valeur émise pour cet événement (utile à une scène qui démarre après coup). */
  last<K extends keyof E>(event: K): E[K] | undefined;
  clear(): void;
}

export function createEventBus<E extends EventMap>(): EventBus<E> {
  const listeners = new Map<keyof E, Set<Listener<never>>>();
  const lastValues = new Map<keyof E, unknown>();

  return {
    emit(event, payload) {
      lastValues.set(event, payload);
      const set = listeners.get(event) as Set<Listener<typeof payload>> | undefined;
      // Copie : un écouteur peut se désabonner pendant l'émission.
      if (set) [...set].forEach((listener) => listener(payload));
    },
    on(event, listener) {
      let set = listeners.get(event);
      if (!set) {
        set = new Set();
        listeners.set(event, set);
      }
      set.add(listener);
      return () => {
        set.delete(listener);
      };
    },
    last(event) {
      return lastValues.get(event) as E[typeof event] | undefined;
    },
    clear() {
      listeners.clear();
      lastValues.clear();
    },
  };
}
