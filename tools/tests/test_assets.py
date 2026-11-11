"""Cohérence des assets générés par tools/assets/build_assets.py (sans Pillow)."""

from __future__ import annotations

import json
from pathlib import Path

import check_map
import pytest

ROOT = Path(__file__).resolve().parents[2]
TILESET = ROOT / "assets" / "tilesets"
SPRITES = ROOT / "assets" / "sprites"
CHARACTERS = ["survivor", "survivor_b", "survivor_c", "survivor_d"]


def test_tileset_table_matches_image() -> None:
    meta = json.loads((TILESET / "valcendre.tiles.json").read_text(encoding="utf-8"))
    w, h = check_map.png_size(TILESET / "valcendre.png")
    assert meta["tilewidth"] == 16 and w == meta["columns"] * 16
    assert meta["tilecount"] <= meta["columns"] * (h // 16)
    idx = sorted(meta["tiles"].values())
    assert idx == list(range(meta["tilecount"])), "index locaux contigus et uniques"
    assert meta["tiles"]["solid"] == 0


def test_map_tileset_matches_table() -> None:
    meta = json.loads((TILESET / "valcendre.tiles.json").read_text(encoding="utf-8"))
    tmj = json.loads(check_map.DEFAULT_MAP.read_text(encoding="utf-8"))
    ts = tmj["tilesets"][0]
    assert ts["tilecount"] == meta["tilecount"] and ts["columns"] == meta["columns"]


@pytest.mark.parametrize("name", CHARACTERS)
def test_character_sheet(name: str) -> None:
    meta = json.loads((SPRITES / f"{name}.json").read_text(encoding="utf-8"))
    w, h = check_map.png_size(SPRITES / f"{name}.png")
    assert (meta["frameWidth"], meta["frameHeight"]) == (16, 16)
    assert (w, h) == (meta["columns"] * 16, meta["rows"] * 16)
    nframes = meta["columns"] * meta["rows"]
    for anim in ("idle", "walk", "run"):
        for d in ("down", "left", "right", "up"):
            a = meta["animations"][f"{anim}_{d}"]
            assert a["frames"] and all(0 <= f < nframes for f in a["frames"])
            assert a["fps"] > 0
