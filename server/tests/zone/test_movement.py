"""Tests du déplacement partagé : fixtures versionnées, propriétés de `step()`, constantes."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path
from typing import Any

import pytest

from app.zone.movement import (
    MOVEMENT_FILE,
    REPO_ROOT,
    CollisionGrid,
    MoveInput,
    MovementConfig,
    normalize_move,
    overlaps_solid,
    step,
)
from app.zone.movement_fixtures import FIXTURES_FILE, build_fixtures, cases, main, render

TOLERANCE = 1e-9
CFG = MovementConfig.load()


def _load_fixtures() -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads((REPO_ROOT / FIXTURES_FILE).read_text(encoding="utf-8"))
    return data


def test_versioned_fixtures_match_implementation() -> None:
    # Si ce test échoue : `uv run python -m app.zone.movement_fixtures`, puis prévenir le client
    # (le port TypeScript de step() doit suivre).
    assert (REPO_ROOT / FIXTURES_FILE).read_text(encoding="utf-8") == render(CFG)
    assert main(["--check"]) == 0


def test_fixtures_cover_contract() -> None:
    fixtures = _load_fixtures()
    assert len(fixtures) >= 12
    names = {case["name"] for case in fixtures}
    assert len(names) == len(fixtures)
    for required in (
        "libre_droite",
        "diagonale_normalisee",
        "sprint",
        "mur_droite",
        "mur_bas",
        "coin",
        "glissement",
        "bord_carte",
        "entree_hors_bornes",
    ):
        assert required in names
    for case in fixtures:
        assert set(case) == {"name", "description", "grid", "start", "dt", "inputs", "expected"}
        assert len(case["inputs"]) == len(case["expected"]) > 0


@pytest.mark.parametrize("case", _load_fixtures(), ids=lambda case: case["name"])
def test_fixture_case(case: dict[str, Any]) -> None:
    """Rejoue un cas exactement comme le fera le client TypeScript."""
    grid = CollisionGrid.from_rows(case["grid"])
    pos = (float(case["start"]["x"]), float(case["start"]["y"]))
    for raw, expected in zip(case["inputs"], case["expected"], strict=True):
        move = MoveInput(float(raw["move_x"]), float(raw["move_y"]), bool(raw["sprint"]))
        pos = step(pos, move, grid, CFG, float(case["dt"]))
        assert abs(pos[0] - expected["x"]) <= TOLERANCE
        assert abs(pos[1] - expected["y"]) <= TOLERANCE
    # Invariant : la position finale est libre (même pour `sortie_de_mur`, parti d'un mur).
    assert not overlaps_solid(pos[0], pos[1], grid, CFG.player_half_size)


def test_exact_contact_values() -> None:
    by_name = {case["name"]: case for case in _load_fixtures()}
    assert by_name["mur_droite"]["expected"][-1] == {"x": 4.7, "y": 3.5}
    assert by_name["mur_gauche"]["expected"][-1] == {"x": 2.3, "y": 2.5}
    assert by_name["mur_bas"]["expected"][-1]["y"] == 4.7
    assert by_name["mur_haut"]["expected"][-1]["y"] == 2.3
    assert by_name["coin"]["expected"][-1] == {"x": 5.7, "y": 3.7}
    assert by_name["bord_carte"]["expected"][-1] == {"x": 0.3, "y": 0.3}
    assert by_name["bord_carte_bas_droite"]["expected"][-1] == {"x": 3.7, "y": 2.7}
    assert by_name["grand_dt"]["expected"][0]["x"] == 5.7


def test_normalize_move() -> None:
    assert normalize_move(0.5, 0.5) == (0.5, 0.5)
    assert normalize_move(1.0, 0.0) == (1.0, 0.0)
    mx, my = normalize_move(1.0, 1.0)
    assert mx == my == 1.0 / math.sqrt(2.0)
    assert normalize_move(5.0, -3.0) == normalize_move(1.0, -1.0)
    assert normalize_move(math.nan, math.inf) == (0.0, 0.0)
    assert normalize_move(-math.inf, 0.2) == (0.0, 0.2)


def test_diagonal_speed_equals_straight_speed() -> None:
    grid = CollisionGrid(20, 20)
    x, y = step((10.0, 10.0), MoveInput(1, 1, False), grid, CFG, 0.05)
    assert math.hypot(x - 10.0, y - 10.0) == pytest.approx(CFG.walk_speed * 0.05, abs=1e-12)
    x, y = step((10.0, 10.0), MoveInput(0, -1, True), grid, CFG, 0.05)
    assert (x, y) == (10.0, 10.0 - CFG.sprint_speed * 0.05)


def test_grid_out_of_bounds_is_solid() -> None:
    grid = CollisionGrid.from_rows(["..", ".#"])
    assert not grid.is_solid(0, 0)
    assert grid.is_solid(1, 1)
    for tx, ty in ((-1, 0), (0, -1), (2, 0), (0, 2)):
        assert grid.is_solid(tx, ty)
    with pytest.raises(ValueError):
        CollisionGrid.from_rows(["..", "."])
    with pytest.raises(ValueError):
        CollisionGrid(2, 2, b"\x00")


def test_never_enters_walls_random() -> None:
    """Propriété : depuis une position libre, aucune suite d'entrées (même extrêmes) n'entre dans un mur."""
    rng = random.Random(1234)
    for _ in range(40):
        rows = ["".join("#" if rng.random() < 0.25 else "." for _ in range(12)) for _ in range(12)]
        grid = CollisionGrid.from_rows(rows)
        free = [(tx + 0.5, ty + 0.5) for ty in range(12) for tx in range(12) if not grid.is_solid(tx, ty)]
        if not free:
            continue
        pos = rng.choice(free)
        for _ in range(200):
            move = MoveInput(rng.uniform(-3, 3), rng.uniform(-3, 3), rng.random() < 0.5)
            pos = step(pos, move, grid, CFG, rng.choice([0.05, 0.05, 0.3, 2.0]))
            assert not overlaps_solid(pos[0], pos[1], grid, CFG.player_half_size), (rows, pos)


def test_config_loading(tmp_path: Path) -> None:
    raw = json.loads((REPO_ROOT / MOVEMENT_FILE).read_text(encoding="utf-8"))
    assert MovementConfig.from_dict(raw) == CFG
    assert CFG.max_inputs_per_tick == 3
    assert CFG.player_half_size == 0.3
    for key, bad in (("walk_speed", "3"), ("player_half_size", 0.5), ("max_inputs_per_tick", 0)):
        with pytest.raises(ValueError):
            MovementConfig.from_dict({**raw, key: bad})
    path = tmp_path / "movement.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        MovementConfig.load(path)


def test_cases_and_build_are_consistent() -> None:
    assert [case["name"] for case in build_fixtures(CFG)] == [case.name for case in cases()]
