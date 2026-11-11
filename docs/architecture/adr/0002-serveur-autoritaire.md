# ADR 0002 — Serveur autoritaire à pas fixe

- Statut : accepté (2026-11-11)

## Décision

- Le client n'envoie que des intentions (entrées, demandes d'action) ; le serveur décide de tout état
  qui compte (positions, dégâts, loot, inventaire, XP).
- Chaque zone exécute une boucle de simulation à pas fixe (`DR_TICK_RATE`, 20 par défaut).
  Les messages de jeu sont mis en file et appliqués au tick suivant ; `ping` est traité immédiatement.
- Le client prédit uniquement son propre déplacement et se réconcilie sur l'accusé `ack_seq` des
  snapshots ; les autres entités sont interpolées avec ~100 ms de retard (phase 2).
- L'accès à une zone passe par un ticket à usage unique délivré par l'API REST (30 s), jamais par le JWT
  dans l'URL du WebSocket.

## Conséquences

- La triche par modification du client ne peut pas créer d'état invalide côté serveur.
- Plusieurs zones pourront tourner dans des processus distincts : Redis portera la présence et les transferts.
