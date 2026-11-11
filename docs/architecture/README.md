# Architecture

## Vue d'ensemble

- **Client** (navigateur) : React gère les écrans et le HUD, Phaser gère le rendu et la prédiction locale.
  Les deux communiquent uniquement par un bus d'événements typé (`client/src/bridge/`).
- **API REST** (FastAPI) : comptes, personnages, choix de zone. Elle délivre un ticket à usage unique
  pour rejoindre une zone.
- **Serveur de zone** (WebSocket) : autoritaire. Il simule le monde à pas fixe (20 ticks/s par défaut),
  valide toute action et diffuse l'état. Une zone = une boucle ; à terme, un processus par zone.
- **PostgreSQL** : source de vérité persistante (migrations Alembic).
- **Redis** : données temporaires (tickets de connexion, puis présence et transferts entre zones).

## Documents

| Document | Contenu |
| --- | --- |
| [conventions.md](conventions.md) | Règles de code, branches, tests, propriété des dossiers |
| [phase-1-contracts.md](phase-1-contracts.md) | Contrats d'interface de la phase 1 |
| [phase-2-contracts.md](phase-2-contracts.md) | Contrats de la phase 2 (carte, déplacement, synchronisation) |
| [phase-3-contracts.md](phase-3-contracts.md) | Contrats de la phase 3 (zombies, combat, loot, inventaire, survie) |
| [protocol.md](protocol.md) | Protocole WebSocket |
| [adr/](adr/) | Décisions d'architecture |
