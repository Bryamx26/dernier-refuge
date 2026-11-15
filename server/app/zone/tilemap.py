"""Chargement des cartes Tiled (`.tmj`, JSON) côté serveur : collisions et points d'apparition.

Sous-ensemble accepté (cf. docs/architecture/phase-2-contracts.md) : carte orthogonale finie,
données de calques en tableaux JSON non compressés. Les calques peuvent être imbriqués dans des
groupes. Le serveur ne lit que :

- le calque de tuiles `collision` : toute tuile non nulle est solide ;
- le calque d'objets `spawns` : objets de type (ou classe, Tiled ≥ 1.9) `player_spawn`, convertis
  de pixels en tuiles (`x / tilewidth`, `y / tileheight` ; centre de l'objet s'il a une taille) ;
- le calque d'objets `buildings` (facultatif) : objets de type `building` avec leur nom et les
  propriétés entières `door_x`, `door_y` (tuile de la porte), utilisés pour la fouille.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.zone.loot import BuildingInfo
from app.zone.movement import CollisionGrid, overlaps_solid

COLLISION_LAYER = "collision"
SPAWNS_LAYER = "spawns"
BUILDINGS_LAYER = "buildings"
PLAYER_SPAWN_TYPE = "player_spawn"
# Dimensions de la carte vide de repli (environnement de test uniquement).
FALLBACK_SIZE = 128


class MapLoadError(Exception):
    """Carte absente, illisible ou hors du format accepté."""


@dataclass(frozen=True)
class ZoneMap:
    """Données de carte utiles à la simulation."""

    map_id: str
    grid: CollisionGrid
    # Points d'apparition des joueurs, en tuiles.
    spawns: list[tuple[float, float]] = field(default_factory=list)
    # Bâtiments à fouiller (portes), en tuiles.
    buildings: list[BuildingInfo] = field(default_factory=list)

    @property
    def width(self) -> int:
        return self.grid.width

    @property
    def height(self) -> int:
        return self.grid.height

    @classmethod
    def open_area(cls, map_id: str, size: int = FALLBACK_SIZE) -> ZoneMap:
        """Carte vide sans obstacle (bords infranchissables), apparition au centre."""
        return cls(map_id=map_id, grid=CollisionGrid(size, size), spawns=[(size / 2, size / 2)])

    def resolve_spawn(self, position: tuple[float, float] | None, half: float) -> tuple[float, float]:
        """Position d'apparition d'un joueur.

        - `position` libre (boîte de demi-côté `half` hors de tout mur et dans la carte) : conservée ;
        - sinon : le point d'apparition libre le plus proche de `position` (le premier si `None`) ;
        - à défaut de point d'apparition libre : le centre de tuile libre le plus proche.
        """
        if position is not None and math.isfinite(position[0]) and math.isfinite(position[1]):
            if not overlaps_solid(position[0], position[1], self.grid, half):
                return position
            origin = position
        else:
            origin = self.spawns[0] if self.spawns else (self.width / 2, self.height / 2)

        def distance2(point: tuple[float, float]) -> float:
            return (point[0] - origin[0]) ** 2 + (point[1] - origin[1]) ** 2

        free_spawns = [s for s in self.spawns if not overlaps_solid(s[0], s[1], self.grid, half)]
        if free_spawns:
            return min(free_spawns, key=distance2)
        free_tiles = [
            (tx + 0.5, ty + 0.5)
            for ty in range(self.height)
            for tx in range(self.width)
            if not self.grid.is_solid(tx, ty)
        ]
        if not free_tiles:
            raise MapLoadError(f"carte {self.map_id} : aucune tuile libre pour faire apparaître un joueur")
        return min(free_tiles, key=distance2)


def _walk_layers(layers: Any) -> Iterator[dict[str, Any]]:
    """Parcourt les calques en profondeur, groupes compris."""
    if not isinstance(layers, list):
        raise MapLoadError("`layers` doit être une liste")
    for layer in layers:
        if not isinstance(layer, dict):
            raise MapLoadError("calque mal formé")
        if layer.get("type") == "group":
            yield from _walk_layers(layer.get("layers", []))
        else:
            yield layer


def _positive_int(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise MapLoadError(f"`{key}` doit être un entier > 0")
    return value


def _number(obj: dict[str, Any], key: str, default: float | None = None) -> float:
    value = obj.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise MapLoadError(f"objet : `{key}` doit être un nombre")
    return float(value)


def _building(obj: dict[str, Any]) -> BuildingInfo | None:
    """Bâtiment d'un objet Tiled, ou None s'il n'a pas de porte."""
    if "building" not in (obj.get("type"), obj.get("class")):
        return None
    props = {p.get("name"): p.get("value") for p in obj.get("properties", []) if isinstance(p, dict)}
    door_x, door_y = props.get("door_x"), props.get("door_y")
    if not isinstance(door_x, int) or not isinstance(door_y, int) or isinstance(door_x, bool):
        return None
    return BuildingInfo(name=str(obj.get("name", ""))[:32], door_x=door_x, door_y=door_y)


def parse_map(data: Any, map_id: str) -> ZoneMap:
    """Construit une `ZoneMap` depuis le JSON Tiled déjà décodé. Lève `MapLoadError`."""
    try:
        if not isinstance(data, dict):
            raise MapLoadError("objet JSON attendu")
        if data.get("orientation", "orthogonal") != "orthogonal":
            raise MapLoadError("seules les cartes orthogonales sont acceptées")
        if data.get("infinite", False):
            raise MapLoadError("les cartes infinies ne sont pas acceptées")
        width, height = _positive_int(data, "width"), _positive_int(data, "height")
        tile_w, tile_h = _positive_int(data, "tilewidth"), _positive_int(data, "tileheight")

        layers = list(_walk_layers(data.get("layers")))
        collision = [
            ly for ly in layers if ly.get("type") == "tilelayer" and ly.get("name") == COLLISION_LAYER
        ]
        if len(collision) != 1:
            raise MapLoadError(f"un et un seul calque de tuiles `{COLLISION_LAYER}` attendu")
        layer = collision[0]
        cells = layer.get("data")
        if layer.get("encoding", "csv") != "csv" or layer.get("compression") or not isinstance(cells, list):
            raise MapLoadError(f"calque `{COLLISION_LAYER}` : tableau de tuiles non compressé attendu")
        if len(cells) != width * height:
            raise MapLoadError(f"calque `{COLLISION_LAYER}` : {len(cells)} tuiles pour {width} × {height}")
        if any(isinstance(c, bool) or not isinstance(c, int) for c in cells):
            raise MapLoadError(f"calque `{COLLISION_LAYER}` : identifiants de tuiles entiers attendus")
        grid = CollisionGrid(width, height, bytes(1 if c != 0 else 0 for c in cells))

        spawns: list[tuple[float, float]] = []
        for group in layers:
            if group.get("type") != "objectgroup" or group.get("name") != SPAWNS_LAYER:
                continue
            objects = group.get("objects", [])
            if not isinstance(objects, list):
                raise MapLoadError(f"calque `{SPAWNS_LAYER}` : liste d'objets attendue")
            for obj in objects:
                if not isinstance(obj, dict):
                    raise MapLoadError(f"calque `{SPAWNS_LAYER}` : objet mal formé")
                if PLAYER_SPAWN_TYPE not in (obj.get("type"), obj.get("class")):
                    continue
                # Point : (x, y) ; rectangle : son centre.
                px = _number(obj, "x") + _number(obj, "width", 0.0) / 2
                py = _number(obj, "y") + _number(obj, "height", 0.0) / 2
                spawns.append((px / tile_w, py / tile_h))
        buildings = [
            building
            for group in layers
            if group.get("type") == "objectgroup" and group.get("name") == BUILDINGS_LAYER
            for obj in group.get("objects", [])
            if isinstance(obj, dict) and (building := _building(obj)) is not None
        ]
        return ZoneMap(map_id=map_id, grid=grid, spawns=spawns, buildings=buildings)
    except MapLoadError as exc:
        raise MapLoadError(f"carte {map_id} : {exc}") from None


def load_map(path: Path) -> ZoneMap:
    """Lit `path` (`maps/<map_id>.tmj`). L'identifiant de carte est le nom du fichier sans extension."""
    map_id = path.stem
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        raise MapLoadError(f"carte {map_id} introuvable : {path}") from None
    except (OSError, ValueError) as exc:
        raise MapLoadError(f"carte {map_id} illisible ({path}) : {exc}") from exc
    return parse_map(data, map_id)
