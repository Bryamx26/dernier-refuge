# Contenu de jeu

Données de gameplay (armes, objets, zombies, tables de loot, recettes, compétences, véhicules), en YAML,
validées par schéma au démarrage du serveur et en CI. Aucune logique ici.

Fichiers (phase 3) : `items.yaml` (armes, munitions, consommables), `zombies.yaml` (types de zombies),
`loot.yaml` (fouille des bâtiments), `survival.yaml` (jauges, inventaire, équipement de départ) et
`zones/<zone_id>.yaml` (peuplement en zombies d’une zone). Le serveur les valide au démarrage
(`server/app/content/`) et refuse de démarrer si un fichier est invalide.
