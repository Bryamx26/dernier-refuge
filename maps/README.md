# Cartes

Cartes au format JSON de [Tiled](https://www.mapeditor.org/) (`.tmj`, Tiled 1.10+), lues par le client
(rendu) et par le serveur (collisions, points d'apparition).

## `valcendre.tmj` — village de Valcendre (zone par défaut)

**Générée, ne pas éditer à la main** : toute modification passe par `tools/mapgen/generate_valcendre.py`
(aléatoire à graine fixe, sortie identique à chaque exécution). Plan et intentions :
`docs/design/world-valcendre.md`.

- 128 × 128 tuiles de 16 px, tileset unique intégré `valcendre` (`../assets/tilesets/valcendre.png`).
- Calques de tuiles : `ground`, `decor`, `above` (au-dessus des personnages : toits, cimes), `collision`
  (masqué ; toute tuile non nulle est solide).
- Calques d'objets : `spawns` (9 points `player_spawn`, place des Cendres) et `buildings`
  (informatif, masqué : rectangle de chaque bâtiment fermé, propriétés `door_x`/`door_y` = case de la
  future porte en phase 3). Les clients peuvent ignorer `buildings`.

### Régénérer et vérifier (depuis la racine du dépôt)

```sh
python3 -I tools/assets/build_assets.py          # si le tileset change (nécessite Pillow + packs Kenney)
python3 tools/mapgen/generate_valcendre.py        # écrit maps/valcendre.tmj (bibliothèque standard)
python3 tools/mapgen/check_map.py                 # contrat : format, bordure, spawns reliés, bâtiments fermés
uv run --project server pytest tools/tests        # tests (dont « la carte versionnée est à jour »)
python3 -I tools/mapgen/render_preview.py maps/valcendre.tmj /tmp/apercu.png [--collision] \
    [--zoom X Y L H --scale 3]                    # aperçu PNG (Pillow)
```

`generate_valcendre.py --check` et `build_assets.py --check` échouent si les fichiers versionnés ne
correspondent plus au code (utilisable en CI). Le générateur n'utilise que des noms de tuiles
(`assets/tilesets/valcendre.tiles.json`) : ajouter une tuile se fait **à la fin** du catalogue de
`build_assets.py` pour ne pas décaler les index.
