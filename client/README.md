# Client — Dernier Refuge

React 18 (écrans, HUD) + Phaser 3 (rendu du jeu) + TypeScript + Vite.

## Lancer

```bash
npm install
npm run dev          # http://localhost:5173, proxy /api et /ws vers VITE_PROXY_TARGET (défaut http://localhost:8000)
```

## Vérifier

```bash
npm run lint
npm run typecheck
npm run test
npm run build
```

## Organisation de `src/`

| Dossier      | Rôle                                                                       |
| ------------ | -------------------------------------------------------------------------- |
| `api/`       | Client REST typé                                                           |
| `net/`       | WebSocket de zone : envoi typé, décodage validé, ping/RTT                  |
| `state/`     | Stores Zustand (session, connexion à la zone)                              |
| `bridge/`    | Bus d'événements typé entre React et Phaser                                |
| `game/`      | Jeu Phaser (scènes) ; n'importe jamais React                               |
| `ui/`        | Écrans, HUD, composants et thème                                           |
| `generated/` | Types du protocole générés par `tools/codegen/generate.py` (ne pas éditer) |
