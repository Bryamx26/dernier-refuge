"""Vérifie une carte Tiled (.tmj) contre le contrat de la phase 2 (docs/architecture/phase-2-contracts.md).

Usage :
  python3 tools/mapgen/check_map.py [maps/valcendre.tmj]

Bibliothèque standard uniquement (utilisable par la CI et par les tests sans dépendance).
Vérifications :
  - format : orthogonale, 128 x 128, tuiles 16 px, non infinie, données non compressées ;
  - calques `ground`, `decor`, `above`, `collision` dans cet ordre, puis l'objet `spawns` ;
  - tileset unique intégré `valcendre`, image relative existante, dimensions cohérentes, gid valides ;
  - `ground` entièrement rempli ;
  - bordure de la carte entièrement solide ;
  - au moins 8 `player_spawn`, sur des cases libres, tous reliés entre eux par des cases libres
    (BFS 4-voisins) ;
  - chaque bâtiment du calque `buildings` est fermé : tout son rectangle est solide, et la case devant
    sa porte (phase 3) est libre et accessible depuis les apparitions ;
  - les sorties de route (est et sud) sont accessibles depuis les apparitions jusqu'aux barricades.
"""

from __future__ import annotations

import json
import struct
import sys
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MAP = ROOT / "maps" / "valcendre.tmj"
TILE_LAYERS = ["ground", "decor", "above", "collision"]


@dataclass
class MapData:
    path: Path
    raw: dict[str, Any]
    width: int
    height: int
    layers: dict[str, dict[str, Any]]
    solid: list[list[bool]] = field(default_factory=list)

    def is_solid(self, x: int, y: int) -> bool:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return True
        return self.solid[y][x]

    def objects(self, layer: str) -> list[dict[str, Any]]:
        return list(self.layers.get(layer, {}).get("objects", []))

    def spawn_tiles(self) -> list[tuple[int, int]]:
        tw = self.raw["tilewidth"]
        return [
            (int(o["x"] // tw), int(o["y"] // tw))
            for o in self.objects("spawns")
            if o.get("type") == "player_spawn"
        ]


def load(path: Path) -> MapData:
    raw = json.loads(path.read_text(encoding="utf-8"))
    w, h = raw["width"], raw["height"]
    layers = {lyr["name"]: lyr for lyr in raw["layers"]}
    m = MapData(path=path, raw=raw, width=w, height=h, layers=layers)
    data = layers["collision"]["data"]
    m.solid = [[data[y * w + x] != 0 for x in range(w)] for y in range(h)]
    return m


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path} n'est pas un PNG")
    w, h = struct.unpack(">II", head[16:24])
    return w, h


def reachable(m: MapData, start: tuple[int, int]) -> set[tuple[int, int]]:
    """Cases libres atteignables depuis `start` par des pas orthogonaux sur des cases libres."""
    if m.is_solid(*start):
        return set()
    seen = {start}
    queue = deque([start])
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if (nx, ny) not in seen and not m.is_solid(nx, ny):
                seen.add((nx, ny))
                queue.append((nx, ny))
    return seen


def check_format(m: MapData) -> list[str]:
    errs: list[str] = []
    r = m.raw
    expect = {
        "orientation": "orthogonal",
        "width": 128,
        "height": 128,
        "tilewidth": 16,
        "tileheight": 16,
        "infinite": False,
        "type": "map",
    }
    for k, v in expect.items():
        if r.get(k) != v:
            errs.append(f"{k} = {r.get(k)!r}, attendu {v!r}")
    names = [lyr["name"] for lyr in r["layers"]]
    tile_names = [lyr["name"] for lyr in r["layers"] if lyr["type"] == "tilelayer"]
    if tile_names != TILE_LAYERS:
        errs.append(f"calques de tuiles {tile_names}, attendu {TILE_LAYERS}")
    if "spawns" not in names or m.layers["spawns"]["type"] != "objectgroup":
        errs.append("calque d'objets `spawns` manquant")
    if len(r["tilesets"]) != 1:
        errs.append("un seul tileset attendu")
        return errs
    ts = r["tilesets"][0]
    if "source" in ts:
        errs.append("tileset externe (.tsx) interdit : il doit être intégré")
        return errs
    if ts.get("name") != "valcendre" or ts.get("firstgid") != 1:
        errs.append("tileset `valcendre` avec firstgid 1 attendu")
    if ts.get("margin", 0) != 0 or ts.get("spacing", 0) != 0 or ts.get("tilewidth") != 16:
        errs.append("tileset : tuiles 16 px sans marge ni espacement attendues")
    image = str(ts.get("image", ""))
    if image.startswith("/") or "://" in image:
        errs.append(f"image du tileset non relative : {image}")
    img_path = (m.path.parent / image).resolve()
    if not img_path.exists():
        errs.append(f"image du tileset introuvable : {img_path}")
    else:
        iw, ih = png_size(img_path)
        if (iw, ih) != (ts["imagewidth"], ts["imageheight"]):
            errs.append(f"dimensions de l'image {iw}x{ih} != tileset {ts['imagewidth']}x{ts['imageheight']}")
        if iw != ts["columns"] * 16 or ts["tilecount"] > ts["columns"] * (ih // 16):
            errs.append("columns/tilecount incohérents avec l'image")
    maxgid = ts["firstgid"] + ts["tilecount"] - 1
    for name in TILE_LAYERS:
        lyr = m.layers.get(name)
        if lyr is None:
            continue
        if "encoding" in lyr or "compression" in lyr:
            errs.append(f"{name} : données compressées interdites")
        data = lyr["data"]
        if len(data) != m.width * m.height:
            errs.append(f"{name} : {len(data)} cases, attendu {m.width * m.height}")
        bad = [g for g in data if not (g == 0 or 1 <= g <= maxgid)]
        if bad:
            errs.append(f"{name} : gid hors tileset (ex. {bad[0]})")
    if 0 in m.layers["ground"]["data"]:
        errs.append("ground : cases vides")
    if m.layers["collision"].get("visible", True):
        errs.append("collision : le calque doit être masqué (visible = false)")
    return errs


def check_border(m: MapData) -> list[str]:
    holes = [
        (x, y)
        for y in range(m.height)
        for x in range(m.width)
        if (x in (0, m.width - 1) or y in (0, m.height - 1)) and not m.solid[y][x]
    ]
    return [f"bordure non solide en {holes[:5]} ({len(holes)} cases)"] if holes else []


def check_spawns(m: MapData) -> list[str]:
    errs: list[str] = []
    objs = m.objects("spawns")
    for o in objs:
        if o.get("type") != "player_spawn":
            errs.append(f"objet {o.get('name')} de type {o.get('type')!r} dans `spawns`")
        if not o.get("point"):
            errs.append(f"spawn {o.get('name')} n'est pas un point")
    spawns = m.spawn_tiles()
    if len(spawns) < 8:
        errs.append(f"{len(spawns)} player_spawn, au moins 8 attendus")
    if len(set(spawns)) != len(spawns):
        errs.append("deux spawns sur la même case")
    blocked = [s for s in spawns if m.is_solid(*s)]
    if blocked:
        errs.append(f"spawns sur des cases solides : {blocked}")
        return errs
    if spawns:
        zone = reachable(m, spawns[0])
        cut = [s for s in spawns if s not in zone]
        if cut:
            errs.append(f"spawns non reliés au premier : {cut}")
    return errs


def check_buildings(m: MapData, min_count: int = 8) -> list[str]:
    errs: list[str] = []
    tw = m.raw["tilewidth"]
    blds = [o for o in m.objects("buildings") if o.get("type") == "building"]
    if not (min_count <= len(blds) <= 10):
        errs.append(f"{len(blds)} bâtiments, attendu {min_count} à 10")
    spawns = m.spawn_tiles()
    zone = reachable(m, spawns[0]) if spawns and not m.is_solid(*spawns[0]) else set()
    above = m.layers["above"]["data"]
    for b in blds:
        x0, y0 = int(b["x"] // tw), int(b["y"] // tw)
        w, h = int(b["width"] // tw), int(b["height"] // tw)
        open_tiles = [(x, y) for y in range(y0, y0 + h) for x in range(x0, x0 + w) if not m.is_solid(x, y)]
        if open_tiles:
            errs.append(f"bâtiment {b['name']} non fermé : cases libres {open_tiles[:4]}")
        roof_missing = [
            (x, y) for y in range(y0, y0 + h - 2) for x in range(x0, x0 + w) if above[y * m.width + x] == 0
        ]
        if roof_missing:
            errs.append(f"bâtiment {b['name']} : toit incomplet")
        props = {p["name"]: p["value"] for p in b.get("properties", [])}
        if "door_x" in props:
            front = (int(props["door_x"]), int(props["door_y"]) + 1)
            if front not in zone:
                errs.append(f"bâtiment {b['name']} : devant de porte {front} inaccessible depuis les spawns")
    return errs


def check_exits(m: MapData) -> list[str]:
    """Les deux routes qui sortent (bord est, bord sud) sont praticables jusqu'à 3 cases du bord."""
    spawns = m.spawn_tiles()
    if not spawns or m.is_solid(*spawns[0]):
        return []
    zone = reachable(m, spawns[0])
    roads = road_tiles(m)
    errs = []
    if not any((m.width - 3, y) in zone for y in range(m.height) if (m.width - 1, y) in roads):
        errs.append("la route de l'est n'est pas accessible jusqu'au bord")
    if not any((x, m.height - 3) in zone for x in range(m.width) if (x, m.height - 1) in roads):
        errs.append("la route du sud n'est pas accessible jusqu'au bord")
    return errs


def road_tiles(m: MapData) -> set[tuple[int, int]]:
    """Cases dont la tuile de sol est une route (noms lus dans <tileset>.tiles.json)."""
    names_path = (m.path.parent / m.raw["tilesets"][0]["image"]).with_suffix(".tiles.json")
    if not names_path.exists():
        return set()
    tiles = json.loads(names_path.read_text(encoding="utf-8"))["tiles"]
    road_gids = {i + 1 for n, i in tiles.items() if n.startswith("road")}
    data = m.layers["ground"]["data"]
    return {(i % m.width, i // m.width) for i, g in enumerate(data) if g in road_gids}


def check_all(m: MapData) -> list[str]:
    errs = check_format(m)
    if errs:
        return errs
    return check_border(m) + check_spawns(m) + check_buildings(m) + check_exits(m)


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_MAP
    m = load(path)
    errs = check_all(m)
    for e in errs:
        print(f"ERREUR : {e}", file=sys.stderr)
    if errs:
        return 1
    free = sum(1 for row in m.solid for s in row if not s)
    zone = reachable(m, m.spawn_tiles()[0])
    print(
        f"OK {path.name} : {m.width}x{m.height}, {len(m.spawn_tiles())} spawns, "
        f"{len(m.objects('buildings'))} bâtiments, {free} cases libres dont {len(zone)} accessibles "
        f"depuis les spawns"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
