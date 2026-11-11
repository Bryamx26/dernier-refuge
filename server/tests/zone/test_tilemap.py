"""Tests du chargement des cartes Tiled (.tmj) côté serveur."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from app.zone.manager import ZoneManager, ZoneSpec
from app.zone.movement import REPO_ROOT, MovementConfig, overlaps_solid
from app.zone.tilemap import MapLoadError, ZoneMap, load_map, parse_map

DATA = Path(__file__).parent / "data"
REAL_MAP = REPO_ROOT / "maps" / "valcendre.tmj"
HALF = MovementConfig.load().player_half_size


def _small() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((DATA / "small.tmj").read_text(encoding="utf-8"))
    return data


def test_load_small_map() -> None:
    zone_map = load_map(DATA / "small.tmj")
    assert zone_map.map_id == "small"
    assert (zone_map.width, zone_map.height) == (8, 6)
    # Bords et bloc central solides (calque `collision` dans un groupe).
    assert zone_map.grid.is_solid(0, 0)
    assert zone_map.grid.is_solid(3, 2) and zone_map.grid.is_solid(4, 2)
    assert not zone_map.grid.is_solid(1, 1)
    # Point (24 px, 24 px) → (1,5 ; 1,5) ; rectangle 16 px en (80, 56) → son centre (5,5 ; 4) ;
    # l'objet d'un autre type est ignoré ; `class` (Tiled ≥ 1.9) vaut `type`.
    assert zone_map.spawns == [(1.5, 1.5), (5.5, 4.0)]


def test_resolve_spawn() -> None:
    zone_map = load_map(DATA / "small.tmj")
    # Position libre : conservée.
    assert zone_map.resolve_spawn((2.0, 3.5), HALF) == (2.0, 3.5)
    # Dans le bloc central, plus proche du second point d'apparition.
    assert zone_map.resolve_spawn((4.6, 2.5), HALF) == (5.5, 4.0)
    # Dans le mur gauche : le premier.
    assert zone_map.resolve_spawn((0.2, 1.0), HALF) == (1.5, 1.5)
    # Hors carte ou non finie.
    assert zone_map.resolve_spawn((-50.0, 400.0), HALF) == (5.5, 4.0)
    assert zone_map.resolve_spawn((float("nan"), 1.0), HALF) == (1.5, 1.5)
    # Aucune position connue : premier point d'apparition.
    assert zone_map.resolve_spawn(None, HALF) == (1.5, 1.5)


def test_resolve_spawn_without_spawns_uses_free_tile() -> None:
    zone_map = ZoneMap(map_id="m", grid=load_map(DATA / "small.tmj").grid, spawns=[(0.5, 0.5)])
    x, y = zone_map.resolve_spawn((3.5, 2.5), HALF)
    assert not overlaps_solid(x, y, zone_map.grid, HALF)
    assert (x, y) in ((3.5, 1.5), (3.5, 3.5), (4.5, 1.5), (4.5, 3.5), (2.5, 2.5))


def test_open_area() -> None:
    zone_map = ZoneMap.open_area("vide", size=16)
    assert zone_map.map_id == "vide"
    assert not zone_map.grid.is_solid(0, 0)
    assert zone_map.grid.is_solid(16, 0)
    assert zone_map.spawns == [(8.0, 8.0)]


def _without_collision(data: dict[str, Any]) -> None:
    data["layers"][1]["layers"].pop(0)


def _wrong_size(data: dict[str, Any]) -> None:
    data["layers"][1]["layers"][0]["data"].pop()


def _compressed(data: dict[str, Any]) -> None:
    layer = data["layers"][1]["layers"][0]
    layer["encoding"], layer["data"] = "base64", "AAAA"


@pytest.mark.parametrize(
    "mutate",
    [
        _without_collision,
        _wrong_size,
        _compressed,
        lambda d: d.update(infinite=True),
        lambda d: d.update(orientation="isometric"),
        lambda d: d.update(width=0),
        lambda d: d.update(layers="non"),
    ],
)
def test_invalid_maps(mutate: Any) -> None:
    data = copy.deepcopy(_small())
    mutate(data)
    with pytest.raises(MapLoadError, match="carte small"):
        parse_map(data, "small")


def test_missing_and_unreadable(tmp_path: Path) -> None:
    with pytest.raises(MapLoadError, match="introuvable"):
        load_map(tmp_path / "absente.tmj")
    bad = tmp_path / "cassee.tmj"
    bad.write_text("{", encoding="utf-8")
    with pytest.raises(MapLoadError, match="illisible"):
        load_map(bad)


@pytest.mark.skipif(not REAL_MAP.exists(), reason="maps/valcendre.tmj pas encore produite")
def test_real_valcendre_map() -> None:
    zone_map = load_map(REAL_MAP)
    assert zone_map.map_id == "valcendre"
    assert (zone_map.width, zone_map.height) == (128, 128)
    assert len(zone_map.spawns) >= 8
    for x, y in zone_map.spawns:
        assert not overlaps_solid(x, y, zone_map.grid, HALF), (x, y)
    # Bords de carte infranchissables (en plus du hors-carte, déjà solide).
    solid_count = sum(zone_map.grid.is_solid(tx, ty) for ty in range(128) for tx in range(128))
    assert 0 < solid_count < 128 * 128


@pytest.mark.skipif(not REAL_MAP.exists(), reason="maps/valcendre.tmj pas encore produite")
async def test_manager_starts_with_real_map() -> None:
    manager = ZoneManager(data_dir=REPO_ROOT)
    spec = ZoneSpec(
        id="valcendre", name="Valcendre", max_players=4, tick_rate=20, map_file="maps/valcendre.tmj"
    )
    await manager.start([spec])
    try:
        zone = manager.get("valcendre")
        assert zone is not None and zone.map.map_id == "valcendre" and zone.map.width == 128
        # Apparition par défaut des personnages (64, 64) : libre, ou remplacée par un spawn libre.
        x, y = zone.map.resolve_spawn((64.0, 64.0), HALF)
        assert not overlaps_solid(x, y, zone.map.grid, HALF)
    finally:
        await manager.stop()
