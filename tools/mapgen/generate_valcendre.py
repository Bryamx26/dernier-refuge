"""Génère maps/valcendre.tmj : le village de Valcendre (JSON Tiled 1.10, 128 x 128 tuiles de 16 px).

Usage (depuis la racine du dépôt) :
  python3 tools/mapgen/generate_valcendre.py           # écrit maps/valcendre.tmj
  python3 tools/mapgen/generate_valcendre.py --check   # échoue si la carte versionnée n'est pas à jour

N'utilise que des NOMS de tuiles, résolus par assets/tilesets/valcendre.tiles.json (produit par
tools/assets/build_assets.py). Aléatoire à graine fixe (SEED) : même code -> même carte, octet pour octet.

Calques (ordre du contrat) : ground, decor, above (dessiné au-dessus des personnages), collision
(non affiché, toute tuile non nulle = solide), puis les calques d'objets `spawns` (player_spawn) et
`buildings` (rectangles des bâtiments fermés, porte prévue pour la phase 3 ; informatif).

Repère : x vers la droite, y vers le bas, en tuiles. Voir docs/design/world-valcendre.md pour le plan.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TILES_JSON = ROOT / "assets" / "tilesets" / "valcendre.tiles.json"
MAP_OUT = ROOT / "maps" / "valcendre.tmj"
TILESET_IMAGE_REL = "../assets/tilesets/valcendre.png"

W = H = 128
SEED = 20260211
SOLID_COVERAGE = 0.30  # une tuile d'objet (voiture…) couvrant au moins 30 % de sa case est solide

# --- Plan du village (en tuiles) ------------------------------------------------------------------
MAIN_Y = 62  # grand-rue est-ouest, 4 de large (62..65), sort à l'est
MAIN_X0 = 30
SOUTH_X = 70  # route du sud, 4 de large (70..73), sort au sud
SOUTH_Y0 = 36
LOW_Y = 80  # rue basse est-ouest (80..83), interne
LOW_X0, LOW_X1 = 44, 101
VILLAGE = (42, 36, 105, 99)  # x0, y0, x1, y1 (exclusif) : trottoirs et lots
PLAZA = (55, 46, 68, 60)  # place des Cendres : points d'apparition


@dataclass(frozen=True)
class Building:
    name: str
    x: int
    y: int
    w: int
    h: int
    wall: str  # red | grey | beige
    roof: str  # red | grey | light | beige


BUILDINGS = [
    Building("Mairie", 44, 47, 10, 13, "red", "red"),
    Building("Épicerie", 77, 49, 9, 11, "grey", "grey"),
    Building("Pharmacie", 89, 51, 11, 9, "beige", "beige"),
    Building("Maison du notaire", 78, 37, 8, 9, "red", "light"),
    Building("Gendarmerie", 45, 68, 10, 10, "grey", "grey"),
    Building("Boulangerie", 57, 68, 9, 10, "beige", "red"),
    Building("Garage Bastide", 77, 68, 11, 10, "red", "grey"),
    Building("Maisons jumelles", 91, 68, 9, 10, "grey", "light"),
    Building("Coopérative agricole", 47, 87, 13, 10, "grey", "grey"),
    Building("École", 78, 88, 12, 9, "beige", "beige"),
]

SOLID_PROPS = {
    "barrel_rust",
    "trash_can",
    "trash_full",
    "bin_dark",
    "tires_stack",
    "hydrant",
    "crate",
    "boxes",
    "barricade_w",
    "barricade_e",
    "planter_base",
    "bush_dark",
    "bush_autumn",
    "bush_light",
}


class Grid:
    def __init__(self, tiles: dict[str, int], coverage: dict[str, float]) -> None:
        self.tiles = tiles
        self.coverage = coverage
        self.ground: list[list[str]] = [["grass_a"] * W for _ in range(H)]
        self.decor: list[list[str | None]] = [[None] * W for _ in range(H)]
        self.above: list[list[str | None]] = [[None] * W for _ in range(H)]
        self.solid: list[list[bool]] = [[False] * W for _ in range(H)]
        self.reserved: list[list[bool]] = [[False] * W for _ in range(H)]  # rien d'aléatoire ici

    def check(self, name: str) -> str:
        if name not in self.tiles:
            raise KeyError(f"tuile inconnue : {name}")
        return name

    def g(self, x: int, y: int, name: str) -> None:
        if 0 <= x < W and 0 <= y < H:
            self.ground[y][x] = self.check(name)

    def d(self, x: int, y: int, name: str, solid: bool | None = None) -> None:
        if not (0 <= x < W and 0 <= y < H):
            return
        self.decor[y][x] = self.check(name)
        if solid is None:
            solid = name in SOLID_PROPS
        if solid:
            self.solid[y][x] = True

    def a(self, x: int, y: int, name: str) -> None:
        if 0 <= x < W and 0 <= y < H:
            self.above[y][x] = self.check(name)

    def free(self, x: int, y: int) -> bool:
        """Case disponible pour un objet aléatoire."""
        return (
            0 <= x < W
            and 0 <= y < H
            and not self.reserved[y][x]
            and not self.solid[y][x]
            and self.decor[y][x] is None
            and self.above[y][x] is None
        )

    def reserve(self, x0: int, y0: int, x1: int, y1: int) -> None:
        for y in range(max(0, y0), min(H, y1)):
            for x in range(max(0, x0), min(W, x1)):
                self.reserved[y][x] = True


class Noise:
    """Bruit de valeur lissé (grille aléatoire + interpolation bilinéaire), déterministe."""

    def __init__(self, rng: random.Random, cell: int) -> None:
        self.cell = cell
        n = W // cell + 2
        self.v = [[rng.random() for _ in range(n)] for _ in range(n)]

    def __call__(self, x: float, y: float) -> float:
        fx, fy = x / self.cell, y / self.cell
        ix, iy = int(fx), int(fy)
        tx, ty = fx - ix, fy - iy
        tx, ty = tx * tx * (3 - 2 * tx), ty * ty * (3 - 2 * ty)
        v = self.v
        a = v[iy][ix] * (1 - tx) + v[iy][ix + 1] * tx
        b = v[iy + 1][ix] * (1 - tx) + v[iy + 1][ix + 1] * tx
        return a * (1 - ty) + b * ty


def in_rect(x: int, y: int, r: tuple[int, int, int, int]) -> bool:
    return r[0] <= x < r[2] and r[1] <= y < r[3]


# --- Briques de construction ----------------------------------------------------------------------


def nine_slice(grid: Grid, prefix: str, x0: int, y0: int, w: int, h: int) -> None:
    for y in range(y0, y0 + h):
        for x in range(x0, x0 + w):
            row = "n" if y == y0 else "s" if y == y0 + h - 1 else ""
            col = "w" if x == x0 else "e" if x == x0 + w - 1 else ""
            grid.g(x, y, f"{prefix}_{(row + col) or 'c'}")


def base_ground(grid: Grid, rng: random.Random) -> None:
    n = Noise(rng, 9)
    for y in range(H):
        for x in range(W):
            v = n(x, y)
            r = rng.random()
            if v > 0.72 and r < 0.5:
                name = "grass_dirty"
            elif r < 0.28:
                name = "grass_b"
            elif r < 0.31:
                name = "grass_dirty"
            else:
                name = "grass_a"
            grid.g(x, y, name)


def forest_mask(rng: random.Random) -> list[list[float]]:
    """Valeur < 1 = forêt (nord-ouest)."""
    n = Noise(rng, 7)
    out = [[9.0] * W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            out[y][x] = (x / 54) ** 2 + (y / 52) ** 2 + (n(x, y) - 0.5) * 0.55
    return out


def road_h(grid: Grid, x0: int, x1: int, y: int, *, line: bool = True) -> None:
    for x in range(x0, x1):
        for dy in range(4):
            name = "road"
            if line and dy == 1:
                name = "road_line_s"
            elif line and dy == 2:
                name = "road_line_n"
            grid.g(x, y + dy, name)
    grid.reserve(x0, y, x1, y + 4)


def road_v(grid: Grid, x: int, y0: int, y1: int, *, line: bool = True) -> None:
    for y in range(y0, y1):
        for dx in range(4):
            name = "road"
            if line and dx == 1:
                name = "road_line_e"
            elif line and dx == 2:
                name = "road_line_w"
            grid.g(x + dx, y, name)
    grid.reserve(x, y0, x + 4, y1)


def sidewalk_rect(grid: Grid, x0: int, y0: int, x1: int, y1: int, rng: random.Random) -> None:
    for y in range(y0, y1):
        for x in range(x0, x1):
            if grid.ground[y][x].startswith("road"):
                continue
            r = rng.random()
            name = "sidewalk"
            if r < 0.06:
                name = "sidewalk_weeds"
            elif r < 0.10:
                name = "sidewalk_litter_a" if r < 0.08 else "sidewalk_litter_b"
            grid.g(x, y, name)
            grid.reserved[y][x] = True


def dirt_track(grid: Grid, rng: random.Random, points: list[tuple[int, int]], width: int = 2) -> None:
    """Chemin de terre entre des points, bords mêlés d'herbe."""
    for (ax, ay), (bx, by) in itertools.pairwise(points):
        steps = max(abs(bx - ax), abs(by - ay)) * 2 + 1
        for i in range(steps + 1):
            t = i / steps
            cx = round(ax + (bx - ax) * t)
            cy = round(ay + (by - ay) * t)
            for dy in range(-1, width + 1):
                for dx in range(-1, width + 1):
                    x, y = cx + dx, cy + dy
                    if not (0 <= x < W and 0 <= y < H) or grid.reserved[y][x]:
                        continue
                    edge = dx in (-1, width) or dy in (-1, width)
                    cur = grid.ground[y][x]
                    if edge:
                        if cur.startswith("grass") and rng.random() < 0.6:
                            grid.g(x, y, "dirt_grassy")
                    else:
                        grid.g(x, y, "dirt_a" if rng.random() < 0.6 else "dirt_b")
                        grid.reserved[y][x] = True


def place_tree(grid: Grid, x: int, y: int, kind: str) -> bool:
    if y < 1 or not grid.free(x, y) or grid.above[y - 1][x] is not None or grid.reserved[y - 1][x]:
        return False
    if grid.ground[y][x].startswith(("road", "sidewalk")):
        return False
    grid.d(x, y, f"tree_{kind}_base", solid=True)
    grid.a(x, y - 1, f"tree_{kind}_top")
    return True


def tree_kind(rng: random.Random, autumn: float = 0.22, light: float = 0.08) -> str:
    r = rng.random()
    return "autumn" if r < autumn else "light" if r < autumn + light else "dark"


def place_car(grid: Grid, color: str, orient: str, x: int, y: int) -> None:
    w, h = (3, 2) if orient == "h" else (2, 2)
    for dy in range(h):
        for dx in range(w):
            name = f"car_{color}_{orient}_{dy}{dx}"
            if grid.coverage[name] <= 0.02:
                continue
            grid.d(x + dx, y + dy, name, solid=grid.coverage[name] >= SOLID_COVERAGE)
    grid.reserve(x - 1, y - 1, x + w + 1, y + h + 1)


def building(grid: Grid, b: Building, rng: random.Random) -> tuple[int, int]:
    """Bâtiment fermé : toit (calque above) + façade sud 2 rangées (ground) ; tout le rectangle est solide.

    Renvoie la case de la porte (dans la rangée basse de la façade)."""
    roof_h = b.h - 2
    for y in range(b.y, b.y + b.h):
        for x in range(b.x, b.x + b.w):
            grid.solid[y][x] = True
            grid.g(x, y, "gravel_a")
    # Toit (9 tranches) + quelques détails
    for y in range(b.y, b.y + roof_h):
        for x in range(b.x, b.x + b.w):
            row = "n" if y == b.y else "s" if y == b.y + roof_h - 1 else ""
            col = "w" if x == b.x else "e" if x == b.x + b.w - 1 else ""
            grid.a(x, y, f"roof_{b.roof}_{(row + col) or 'c'}")
    for _ in range(rng.randint(1, 3)):
        vx = rng.randint(b.x + 1, b.x + b.w - 2)
        vy = rng.randint(b.y + 1, b.y + roof_h - 2)
        grid.a(vx, vy, f"roof_{b.roof}_{rng.choice(['vent', 'hatch'])}")
    # Façade
    top_y, base_y = b.y + b.h - 2, b.y + b.h - 1
    for x in range(b.x, b.x + b.w):
        part = "w" if x == b.x else "e" if x == b.x + b.w - 1 else "c"
        grid.g(x, top_y, f"wall_{b.wall}_top_{part}")
        grid.g(x, base_y, f"wall_{b.wall}_base_{part}")
    door_x = b.x + b.w // 2 + rng.choice([-1, 0, 1])
    grid.d(
        door_x,
        base_y,
        rng.choice(
            [
                "door_glass",
                "door_glass_broken",
                "door_wood",
                "door_wood_broken",
                "door_dark",
                "door_wood_round",
            ]
        ),
        solid=True,
    )
    for x in range(b.x + 1, b.x + b.w - 1):
        if (x - b.x) % 2 == 1:
            grid.d(x, top_y, "window_broken" if rng.random() < 0.4 else "window", solid=True)
        if x not in (door_x - 1, door_x, door_x + 1) and (x - b.x) % 3 == 1 and rng.random() < 0.6:
            grid.d(x, base_y, "window_tall_broken" if rng.random() < 0.5 else "window_small", solid=True)
    grid.reserve(b.x - 1, b.y - 1, b.x + b.w + 1, b.y + b.h + 1)
    return door_x, base_y


# --- Génération -----------------------------------------------------------------------------------


def generate(
    tiles: dict[str, int], coverage: dict[str, float]
) -> tuple[Grid, list[tuple[int, int]], list[tuple[Building, int, int]]]:
    rng = random.Random(SEED)
    grid = Grid(tiles, coverage)
    base_ground(grid, rng)
    forest = forest_mask(rng)

    # Sol de forêt
    for y in range(H):
        for x in range(W):
            if forest[y][x] < 1:
                r = rng.random()
                if forest[y][x] < 0.85 or r < 0.5:
                    grid.g(x, y, "grass_dark_a" if r < 0.6 else "grass_dark_b")

    # Parcelles de terre (champs en friche au sud-est, taches ailleurs)
    fields = [(108, 72, 9, 6), (108, 81, 9, 6), (108, 90, 14, 5), (110, 99, 11, 6), (111, 108, 9, 7)]
    for fx, fy, fw, fh in fields:
        nine_slice(grid, "dpatch", fx, fy, fw, fh)
    for _ in range(26):
        pw, ph = rng.randint(3, 6), rng.randint(3, 4)
        px, py = rng.randint(4, W - 4 - pw), rng.randint(4, H - 4 - ph)
        if forest[py][px] < 1.1 or in_rect(px, py, (36, 30, 110, 104)) or (px > 104 and 68 < py < 118):
            continue
        nine_slice(grid, "dpatch", px, py, pw, ph)

    # Routes
    road_h(grid, MAIN_X0, W, MAIN_Y)
    road_v(grid, SOUTH_X, SOUTH_Y0, H)
    road_h(grid, LOW_X0, LOW_X1, LOW_Y)
    # Trottoirs (dans le village seulement)
    vx0, vy0, vx1, vy1 = VILLAGE
    sidewalk_rect(grid, vx0, MAIN_Y - 2, vx1, MAIN_Y, rng)
    sidewalk_rect(grid, vx0, MAIN_Y + 4, vx1, MAIN_Y + 6, rng)
    sidewalk_rect(grid, LOW_X0 - 2, LOW_Y - 2, LOW_X1 + 2, LOW_Y, rng)
    sidewalk_rect(grid, LOW_X0 - 2, LOW_Y + 4, LOW_X1 + 2, LOW_Y + 6, rng)
    sidewalk_rect(grid, LOW_X0 - 2, LOW_Y, LOW_X0, LOW_Y + 4, rng)
    sidewalk_rect(grid, SOUTH_X - 2, vy0, SOUTH_X, vy1, rng)
    sidewalk_rect(grid, SOUTH_X + 4, vy0, SOUTH_X + 6, vy1, rng)
    # Carrefours : intérieur sans ligne, passages piétons autour
    for cy in (MAIN_Y, LOW_Y):
        for y in range(cy, cy + 4):
            for x in range(SOUTH_X, SOUTH_X + 4):
                grid.g(x, y, "road")
        for y in range(cy, cy + 4):
            grid.g(SOUTH_X - 2, y, "road_xwalk_ns")
            grid.g(SOUTH_X + 5, y, "road_xwalk_ns")
        for x in range(SOUTH_X, SOUTH_X + 4):
            grid.g(x, cy - 2, "road_xwalk_ew")
            grid.g(x, cy + 5, "road_xwalk_ew")
    # Usure de la chaussée : herbe, nids-de-poule, plaques
    for y in range(H):
        for x in range(W):
            name = grid.ground[y][x]
            if name != "road":
                continue
            outside = not in_rect(x, y, VILLAGE)
            r = rng.random()
            if r < (0.16 if outside else 0.04):
                grid.g(x, y, "road_weeds_b" if rng.random() < 0.35 else "road_weeds_a")
            elif r < (0.19 if outside else 0.06):
                grid.g(x, y, "road_patch")
    for mx, my in [
        (56, MAIN_Y),  # hors des rangées de ligne jaune
        (88, MAIN_Y + 3),
        (SOUTH_X, 92),
        (SOUTH_X + 3, 110),
        (60, LOW_Y + 3),
    ]:
        grid.g(mx, my, "road_manhole")

    # Chemins de terre : forêt (ouest), clairière (nord), champs (est), casse (sud-ouest)
    dirt_track(grid, rng, [(MAIN_X0, MAIN_Y + 1), (24, 60), (21, 50), (24, 40), (18, 30), (12, 20), (16, 8)])
    dirt_track(grid, rng, [(SOUTH_X + 1, SOUTH_Y0), (SOUTH_X + 1, 30), (SOUTH_X + 1, 24)])
    dirt_track(grid, rng, [(LOW_X1, LOW_Y + 1), (106, LOW_Y + 1), (116, 88)])
    dirt_track(grid, rng, [(LOW_X0 - 2, LOW_Y + 1), (36, 86), (32, 94)])
    nine_slice(grid, "dpatch", 62, 16, 19, 9)  # clairière du campement
    grid.reserve(63, 17, 80, 24)

    # Place des Cendres (apparitions)
    px0, py0, px1, py1 = PLAZA
    for y in range(py0, py1):
        for x in range(px0, px1):
            r = rng.random()
            grid.g(x, y, "sidewalk_b" if r < 0.9 else "sidewalk_weeds" if r < 0.95 else "gravel_b")
    grid.reserve(px0, py0, px1, py1)
    for cx, cy in [(px0 + 1, py0 + 1), (px1 - 2, py0 + 1), (px0 + 1, py1 - 2), (px1 - 2, py1 - 2)]:
        grid.d(cx, cy, "planter_base", solid=True)
        grid.a(cx, cy - 1, "tree_dark_top")
    for x, y, name in [
        (px0, py0, "crate"),
        (px0 + 1, py0, "boxes"),
        (px1 - 1, py0 + 5, "barrel_rust"),
        (px1 - 1, py0 + 6, "barrel_rust"),
        (px0, py1 - 4, "trash_full"),
        (px0 + 6, py0, "debris"),
        (px0 + 4, py1 - 1, "rubble"),
    ]:
        grid.d(x, y, name)
    spawns = [(x, y) for y in (py0 + 4, py0 + 7, py0 + 10) for x in (px0 + 3, px0 + 6, px0 + 9)]

    # Lots du village : gravier et herbe sale autour des bâtiments
    lots = Noise(rng, 4)
    for y in range(vy0, vy1):
        for x in range(vx0, vx1):
            if not grid.reserved[y][x] and grid.ground[y][x].startswith("grass"):
                v = lots(x, y)
                if v > 0.6:
                    grid.g(x, y, "gravel_a" if rng.random() < 0.6 else "gravel_b")
                elif v > 0.5:
                    grid.g(x, y, "dirt_grassy" if rng.random() < 0.7 else "grass_dirty")

    # Bâtiments
    doors: list[tuple[Building, int, int]] = []
    for b in BUILDINGS:
        dx, dy = building(grid, b, rng)
        doors.append((b, dx, dy))
        # parvis devant la porte : dégagé
        for x in range(dx - 1, dx + 2):
            if not grid.ground[dy + 1][x].startswith(("road", "sidewalk")):
                grid.g(x, dy + 1, "gravel_b")
        grid.reserve(dx - 1, dy + 1, dx + 2, dy + 3)

    # Bordure : deux rangées solides (haie d'arbres), barricades aux sorties de route
    exits = {(x, y) for x in (W - 2, W - 1) for y in range(MAIN_Y, MAIN_Y + 4)}
    exits |= {(x, y) for y in (H - 2, H - 1) for x in range(SOUTH_X, SOUTH_X + 4)}
    for y in range(H):
        for x in range(W):
            ring = min(x, y, W - 1 - x, H - 1 - y)
            if ring > 1:
                continue
            grid.solid[y][x] = True
            if (x, y) in exits:
                continue
            if grid.ground[y][x].startswith(("road", "sidewalk", "dirt", "dpatch")):
                grid.g(x, y, "grass_b")
    for y in range(H):
        for x in range(W):
            ring = min(x, y, W - 1 - x, H - 1 - y)
            if ring > 2 or (x, y) in exits or (ring == 2 and not grid.free(x, y)):
                continue
            if ring == 2 and grid.ground[y][x].startswith(("road", "dirt")):
                continue
            outer = x in (0, W - 1) or y in (0, H - 1)
            if (outer or y == 1) and grid.decor[y][x] is None and rng.random() < 0.85:
                grid.d(x, y, rng.choice(["bush_dark", "bush_dark", "bush_autumn"]), solid=True)
            if not outer and y >= 2 and grid.decor[y][x] is None and (ring == 1 or rng.random() < 0.5):
                k = tree_kind(rng, 0.25, 0.05)
                grid.d(x, y, f"tree_{k}_base", solid=True)
                if grid.above[y - 1][x] is None:
                    grid.a(x, y - 1, f"tree_{k}_top")
    for i, y in enumerate(range(MAIN_Y, MAIN_Y + 4)):
        grid.d(W - 2, y, "barricade_w" if i % 2 == 0 else "barricade_e", solid=True)
    for i, x in enumerate(range(SOUTH_X, SOUTH_X + 4)):
        grid.d(x, H - 2, "barricade_w" if i % 2 == 0 else "barricade_e", solid=True)
    grid.d(W - 4, MAIN_Y + 1, "cone")
    grid.d(W - 5, MAIN_Y + 3, "cone")
    grid.d(SOUTH_X + 2, H - 4, "cone")
    grid.reserve(0, 0, W, 2)
    grid.reserve(0, H - 2, W, H)
    grid.reserve(0, 0, 2, H)
    grid.reserve(W - 2, 0, W, H)

    # Voitures abandonnées (certaines en travers), avant les arbres et le désordre
    cars = [
        ("orange", "h", 49, MAIN_Y + 2),
        ("green", "v", 60, MAIN_Y),
        ("grey", "h", 83, MAIN_Y),
        ("green", "h", 95, MAIN_Y + 2),
        ("grey", "v", 109, MAIN_Y + 1),
        ("orange", "h", 117, MAIN_Y),
        ("green", "h", 120, MAIN_Y + 2),
        ("grey", "v", SOUTH_X, 89),
        ("orange", "v", SOUTH_X + 2, 103),
        ("green", "h", SOUTH_X, 112),
        ("grey", "v", SOUTH_X + 2, 120),
        ("orange", "v", 61, LOW_Y),
        ("grey", "h", 86, LOW_Y + 2),
        ("green", "v", 38, MAIN_Y),
        ("orange", "h", 66, 19),
    ]
    for color, orient, x, y in cars:
        place_car(grid, color, orient, x, y)
    # Casse au sud-ouest : épaves et pneus sur gravier
    jx0, jy0, jx1, jy1 = 14, 94, 34, 114
    for y in range(jy0, jy1):
        for x in range(jx0, jx1):
            r = rng.random()
            edge = x in (jx0, jx1 - 1) or y in (jy0, jy1 - 1)
            if edge and r < 0.45:
                continue  # bord irrégulier : l'herbe reprend
            grid.g(x, y, "gravel_a" if r < 0.5 else "gravel_b" if r < 0.8 else "rubble_ground")
    for color, orient, x, y in [
        ("grey", "h", 16, 96),
        ("orange", "v", 22, 96),
        ("green", "h", 27, 97),
        ("orange", "h", 16, 102),
        ("green", "v", 26, 103),
        ("grey", "h", 18, 108),
        ("grey", "v", 29, 109),
    ]:
        place_car(grid, color, orient, x, y)
    grid.reserve(jx0, jy0, jx1, jy1)
    for _ in range(40):
        x, y = rng.randrange(jx0, jx1), rng.randrange(jy0, jy1)
        if grid.decor[y][x] is None and not grid.solid[y][x]:
            grid.d(x, y, rng.choice(["tire", "tires_stack", "barrel_rust", "debris", "rubble", "tire"]))

    # Arbres : forêt dense au nord-ouest, bosquets ailleurs
    groves = Noise(rng, 6)
    for cy in range(2, H - 2, 2):
        for cx in range(2, W - 2, 2):
            x, y = cx + rng.randint(0, 1), cy + rng.randint(0, 1)
            f = forest[y][x]
            if in_rect(x, y, (VILLAGE[0] - 2, VILLAGE[1] - 2, VILLAGE[2] + 2, VILLAGE[3] + 2)):
                p = 0.02
            elif f < 0.7:
                p = 0.88
            elif f < 1:
                p = 0.55
            elif f < 1.25:
                p = 0.12
            elif groves(x, y) > 0.74:
                p = 0.5
            else:
                p = 0.03
            if rng.random() < p:
                place_tree(grid, x, y, tree_kind(rng, 0.2 if f < 1 else 0.4, 0.06))
            elif f < 1 and rng.random() < 0.18 and grid.free(x, y):
                grid.d(x, y, "bush_dark" if rng.random() < 0.8 else "bush_autumn", solid=True)

    # Désordre : débris sur la route, poubelles et caisses dans les lots, buissons dans les champs
    for y in range(2, H - 2):
        for x in range(2, W - 2):
            if not grid.free(x, y) and not (grid.reserved[y][x] and grid.ground[y][x].startswith(("road",))):
                continue
            if grid.decor[y][x] is not None or grid.solid[y][x]:
                continue
            gname = grid.ground[y][x]
            r = rng.random()
            if gname.startswith("road") and not in_rect(x, y, PLAZA):
                if r < 0.012:
                    grid.d(x, y, rng.choice(["debris", "rubble", "tire"]))
            elif in_rect(x, y, VILLAGE) and not grid.reserved[y][x]:
                if r < 0.05:
                    grid.d(
                        x,
                        y,
                        rng.choice(
                            [
                                "trash_full",
                                "barrel_rust",
                                "crate",
                                "boxes",
                                "tires_stack",
                                "bin_dark",
                                "debris",
                                "rubble",
                            ]
                        ),
                    )
            elif gname.startswith("dpatch") and y % 2 == 0 and not grid.reserved[y][x]:
                if r < 0.35:
                    grid.d(x, y, rng.choice(["bush_autumn", "bush_light", "bush_autumn"]), solid=True)
            elif gname.startswith("grass") and not grid.reserved[y][x] and r < 0.006:
                grid.d(x, y, rng.choice(["rubble", "debris", "tire"]))
    # Trottoirs : poubelles près des portes, bouches d'incendie aux angles
    for x, y in [(66, MAIN_Y - 1), (76, MAIN_Y - 2), (76, MAIN_Y + 5), (66, LOW_Y - 1), (102, LOW_Y - 2)]:
        grid.d(x, y, "hydrant")
    for b, dx, dy in doors:
        for tx in (dx - 3, dx + 3):
            ty = dy + 1
            if (
                0 < ty < H
                and grid.decor[ty][tx] is None
                and not grid.solid[ty][tx]
                and rng.random() < 0.5
                and b.x <= tx < b.x + b.w
            ):
                grid.d(tx, ty, rng.choice(["trash_can", "trash_full", "boxes"]))
    # Campement abandonné dans la clairière nord
    for x, y, name in [
        (64, 17, "crate"),
        (65, 17, "boxes"),
        (64, 18, "barrel_rust"),
        (77, 18, "tires_stack"),
        (78, 22, "barrel_rust"),
        (72, 21, "debris"),
        (75, 17, "crate"),
        (63, 23, "trash_full"),
    ]:
        grid.d(x, y, name)
    return grid, spawns, doors


# --- Sérialisation Tiled --------------------------------------------------------------------------


def to_tmj(
    grid: Grid, spawns: list[tuple[int, int]], doors: list[tuple[Building, int, int]], meta: dict[str, object]
) -> dict[str, object]:
    tiles = grid.tiles

    def gid(name: str | None) -> int:
        return 0 if name is None else tiles[name] + 1

    def layer(
        lid: int, name: str, rows: list[list[str | None]] | list[list[str]], visible: bool = True
    ) -> dict[str, object]:
        return {
            "id": lid,
            "name": name,
            "type": "tilelayer",
            "x": 0,
            "y": 0,
            "width": W,
            "height": H,
            "opacity": 1,
            "visible": visible,
            "data": [gid(n) for row in rows for n in row],
        }

    collision_rows: list[list[str | None]] = [["solid" if s else None for s in row] for row in grid.solid]
    objects = []
    oid = 1
    for i, (x, y) in enumerate(spawns, start=1):
        objects.append(
            {
                "id": oid,
                "name": f"spawn_{i}",
                "type": "player_spawn",
                "point": True,
                "x": (x + 0.5) * 16,
                "y": (y + 0.5) * 16,
                "width": 0,
                "height": 0,
                "rotation": 0,
                "visible": True,
            }
        )
        oid += 1
    bobjects = []
    for b, dx, dy in doors:
        bobjects.append(
            {
                "id": oid,
                "name": b.name,
                "type": "building",
                "x": b.x * 16,
                "y": b.y * 16,
                "width": b.w * 16,
                "height": b.h * 16,
                "rotation": 0,
                "visible": True,
                "properties": [
                    {"name": "door_x", "type": "int", "value": dx},
                    {"name": "door_y", "type": "int", "value": dy},
                ],
            }
        )
        oid += 1
    image_w = int(meta["columns"]) * 16  # type: ignore[call-overload]
    tilecount = int(meta["tilecount"])  # type: ignore[call-overload]
    image_h = math.ceil(tilecount / int(meta["columns"])) * 16  # type: ignore[call-overload]
    return {
        "compressionlevel": -1,
        "type": "map",
        "version": "1.10",
        "tiledversion": "1.10.2",
        "orientation": "orthogonal",
        "renderorder": "right-down",
        "infinite": False,
        "width": W,
        "height": H,
        "tilewidth": 16,
        "tileheight": 16,
        "properties": [
            {"name": "map_id", "type": "string", "value": "valcendre"},
            {
                "name": "generator",
                "type": "string",
                "value": f"tools/mapgen/generate_valcendre.py (graine {SEED}) — ne pas éditer à la main",
            },
        ],
        "layers": [
            layer(1, "ground", grid.ground),
            layer(2, "decor", grid.decor),
            layer(3, "above", grid.above),
            layer(4, "collision", collision_rows, visible=False),
            {
                "id": 5,
                "name": "spawns",
                "type": "objectgroup",
                "draworder": "topdown",
                "x": 0,
                "y": 0,
                "opacity": 1,
                "visible": True,
                "objects": objects,
            },
            {
                "id": 6,
                "name": "buildings",
                "type": "objectgroup",
                "draworder": "topdown",
                "x": 0,
                "y": 0,
                "opacity": 1,
                "visible": False,
                "objects": bobjects,
            },
        ],
        "nextlayerid": 7,
        "nextobjectid": oid,
        "tilesets": [
            {
                "firstgid": 1,
                "name": "valcendre",
                "image": TILESET_IMAGE_REL,
                "imagewidth": image_w,
                "imageheight": image_h,
                "tilewidth": 16,
                "tileheight": 16,
                "tilecount": tilecount,
                "columns": meta["columns"],
                "margin": 0,
                "spacing": 0,
            }
        ],
    }


def _pretty(obj: object, indent: int = 0) -> str:
    """JSON lisible, une rangée de tuiles par ligne dans les tableaux `data` (diffs raisonnables)."""
    pad = " " * indent
    if isinstance(obj, dict):
        items = []
        for k, v in obj.items():
            if k == "data" and isinstance(v, list):
                rows = [",".join(str(n) for n in v[i : i + W]) for i in range(0, len(v), W)]
                inner = (",\n" + pad + "  ").join(rows)
                items.append(f'{pad} "data": [\n{pad}  {inner}\n{pad} ]')
            else:
                items.append(f"{pad} {json.dumps(k, ensure_ascii=False)}: {_pretty(v, indent + 1).lstrip()}")
        return "{\n" + ",\n".join(items) + "\n" + pad + "}"
    if isinstance(obj, list) and obj and isinstance(obj[0], dict):
        return "[\n" + ",\n".join(pad + " " + _pretty(v, indent + 1).lstrip() for v in obj) + "\n" + pad + "]"
    return json.dumps(obj, ensure_ascii=False)


def build() -> bytes:
    meta = json.loads(TILES_JSON.read_text(encoding="utf-8"))
    grid, spawns, doors = generate(meta["tiles"], meta["coverage"])
    return (_pretty(to_tmj(grid, spawns, doors, meta)) + "\n").encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--check", action="store_true", help="vérifie que maps/valcendre.tmj est à jour")
    parser.add_argument("--out", type=Path, default=MAP_OUT)
    args = parser.parse_args()
    data = build()
    if args.check:
        if not args.out.exists() or args.out.read_bytes() != data:
            print(f"pas à jour : {args.out} (relancez tools/mapgen/generate_valcendre.py)", file=sys.stderr)
            return 1
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(data)
    print(f"écrit {args.out} ({len(data)} octets)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
