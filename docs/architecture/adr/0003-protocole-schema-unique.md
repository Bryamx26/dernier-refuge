# ADR 0003 — Protocole décrit par un schéma unique

- Statut : accepté (2026-11-11)

## Décision

`shared/protocol/protocol.json` décrit chaque message (sous-ensemble de JSON Schema). Le script
`tools/codegen/generate.py` produit les modèles Pydantic (validation serveur) et les types TypeScript.
La CI échoue si les fichiers générés ne sont pas à jour.

Encodage JSON pour démarrer ; MessagePack pourra le remplacer en phase 7 sans changer le schéma.

## Conséquences

- Un message ne peut pas exister d'un seul côté.
- Le générateur refuse tout mot-clé qu'il ne sait pas traduire, pour qu'aucune contrainte ne soit ignorée.
