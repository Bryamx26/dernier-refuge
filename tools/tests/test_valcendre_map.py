"""Vérifie maps/valcendre.tmj (contrat phase 2) et la détection d'erreurs de check_map."""

from __future__ import annotations

import copy

import check_map
import generate_valcendre
import pytest

MAP = check_map.DEFAULT_MAP


@pytest.fixture(scope="module")
def m() -> check_map.MapData:
    return check_map.load(MAP)


def fresh() -> check_map.MapData:
    m = check_map.load(MAP)
    m.raw = copy.deepcopy(m.raw)
    return m


def test_map_is_up_to_date() -> None:
    assert MAP.read_bytes() == generate_valcendre.build(), "relancer tools/mapgen/generate_valcendre.py"


def test_format(m: check_map.MapData) -> None:
    assert check_map.check_format(m) == []


def test_border_is_solid(m: check_map.MapData) -> None:
    assert check_map.check_border(m) == []


def test_spawns_free_and_connected(m: check_map.MapData) -> None:
    assert len(m.spawn_tiles()) >= 8
    assert check_map.check_spawns(m) == []


def test_buildings_closed_and_doors_reachable(m: check_map.MapData) -> None:
    assert 8 <= len(m.objects("buildings")) <= 10
    assert check_map.check_buildings(m) == []


def test_road_exits_reachable(m: check_map.MapData) -> None:
    assert check_map.check_exits(m) == []


def test_everything(m: check_map.MapData) -> None:
    assert check_map.check_all(m) == []


# --- Le vérificateur détecte bien les erreurs -----------------------------------------------------


def test_detects_open_building() -> None:
    m = fresh()
    b = m.objects("buildings")[0]
    x, y = int(b["x"] // 16) + 2, int(b["y"] // 16) + 2
    m.solid[y][x] = False
    assert any("non fermé" in e for e in check_map.check_buildings(m))


def test_detects_border_hole() -> None:
    m = fresh()
    m.solid[0][50] = False
    assert check_map.check_border(m)


def test_detects_spawn_in_wall() -> None:
    m = fresh()
    x, y = m.spawn_tiles()[3]
    m.solid[y][x] = True
    assert any("solides" in e for e in check_map.check_spawns(m))


def test_detects_isolated_spawn() -> None:
    m = fresh()
    x, y = m.spawn_tiles()[4]
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        m.solid[y + dy][x + dx] = True
    assert any("non reliés" in e for e in check_map.check_spawns(m))


def test_detects_external_tileset() -> None:
    m = fresh()
    m.raw["tilesets"][0] = {"firstgid": 1, "source": "valcendre.tsx"}
    assert any("externe" in e for e in check_map.check_format(m))
