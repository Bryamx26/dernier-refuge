"""Construit les assets graphiques de Valcendre depuis les packs Kenney (CC0).

Sorties (versionnées) :
  - assets/tilesets/valcendre.png        tuiles 16 px assemblées en grille, sans marge ni espacement
  - assets/tilesets/valcendre.tiles.json table nom -> index local (+ provenance, couverture)
  - assets/sprites/survivor*.png + .json spritesheets des personnages jouables

Usage :
  python3 -I tools/assets/build_assets.py [CHEMIN_SOURCES_KENNEY_2D]
  python3 -I tools/assets/build_assets.py --check   # échoue si les sorties ne sont pas à jour

Le chemin des sources pointe sur le dossier `2d` du miroir Kenney (contient
« Roguelike City Pack/Tiles » et « RPG Urban Pack/Tiles »). Ce script ne fait que
LIRE des PNG dans ce dossier ; lancez-le avec `python3 -I` et jamais depuis ce dossier.

Le script est déterministe : même sources -> mêmes octets. Un étalonnage « post-apo »
(désaturation, assombrissement, léger virage olive) est appliqué aux tuiles du décor ;
les personnages gardent leurs couleurs d'origine pour rester lisibles sur le fond sombre.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from collections.abc import Callable
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SRC = Path("/tmp/claude-0/assets-src/kenney/2d")
TILESET_PNG = ROOT / "assets" / "tilesets" / "valcendre.png"
TILESET_JSON = ROOT / "assets" / "tilesets" / "valcendre.tiles.json"
SPRITES_DIR = ROOT / "assets" / "sprites"

TILE = 16
TILESET_COLUMNS = 16

CITY = "Roguelike City Pack/Tiles"
URBAN = "RPG Urban Pack/Tiles"
URBAN_COLUMNS = 27

# Étalonnage du décor : 0 = couleurs Kenney d'origine.
GRADE_DESATURATE = 0.38
GRADE_BRIGHTNESS = 0.78
GRADE_TINT = (1.00, 1.02, 0.92)  # léger virage olive / cendre
GRADE_DRY = 0.45  # les verts tirent vers l'olive : herbe sèche, végétation fatiguée

Source = tuple[str, int] | tuple[str, Callable[["Loader"], Image.Image]]


class Loader:
    def __init__(self, src: Path) -> None:
        self.src = src
        self._cache: dict[tuple[str, int], Image.Image] = {}

    def tile(self, pack: str, index: int) -> Image.Image:
        key = (pack, index)
        if key not in self._cache:
            path = self.src / pack / f"tile_{index:04d}.png"
            with Image.open(path) as im:
                img = im.convert("RGBA")
            if img.size != (TILE, TILE):
                raise ValueError(f"{path}: taille {img.size}, attendu {TILE}x{TILE}")
            self._cache[key] = img
        return self._cache[key].copy()

    def city(self, index: int) -> Image.Image:
        return self.tile(CITY, index)


# --- Tuiles dérivées (composées à partir de tuiles CC0) -------------------------------------------


def _green_pixels_onto(base: int, grass_src: int) -> Callable[[Loader], Image.Image]:
    """Asphalte/trottoir envahi : copie les pixels « herbe » d'une tuile mixte terre/herbe."""

    def build(ld: Loader) -> Image.Image:
        out = ld.city(base)
        grass = ld.city(grass_src)
        px_out = out.load()
        px_g = grass.load()
        assert px_out is not None and px_g is not None
        for y in range(TILE):
            for x in range(TILE):
                r, g, b, a = px_g[x, y]
                if a and g > r + 20:
                    px_out[x, y] = (r, g, b, 255)
        return out

    return build


def _overlay(base: int, top: int) -> Callable[[Loader], Image.Image]:
    def build(ld: Loader) -> Image.Image:
        out = ld.city(base)
        out.alpha_composite(ld.city(top))
        return out

    return build


def _speckles_onto(base: int, grass_src: int) -> Callable[[Loader], Image.Image]:
    """Herbe clairsemée plus dense : pixels « herbe » d'une tuile + ceux de son miroir."""

    def build(ld: Loader) -> Image.Image:
        out = ld.city(base)
        grass = ld.city(grass_src)
        mirrored = grass.transpose(Image.Transpose.ROTATE_180)
        px_out = out.load()
        assert px_out is not None
        for src in (grass, mirrored):
            px_g = src.load()
            assert px_g is not None
            for y in range(TILE):
                for x in range(TILE):
                    r, g, b, a = px_g[x, y]
                    if a and g > r + 20:
                        px_out[x, y] = (r, g, b, 255)
        return out

    return build


def _darker(base: int, factor: float) -> Callable[[Loader], Image.Image]:
    def build(ld: Loader) -> Image.Image:
        out = ld.city(base)
        px = out.load()
        assert px is not None
        for y in range(TILE):
            for x in range(TILE):
                r, g, b, a = px[x, y]
                px[x, y] = (round(r * factor), round(g * factor), round(b * factor), a)
        return out

    return build


def _solid_marker(_: Loader) -> Image.Image:
    """Tuile du calque `collision` (non affiché en jeu) : rouge translucide barré, visible dans Tiled."""
    img = Image.new("RGBA", (TILE, TILE), (200, 30, 30, 110))
    px = img.load()
    assert px is not None
    for i in range(TILE):
        px[i, i] = (255, 60, 60, 200)
        px[TILE - 1 - i, i] = (255, 60, 60, 200)
    return img


# --- Catalogue : nom -> source. L'ordre fixe les index locaux (ne réordonnez pas : ajoutez à la fin). -


def catalog() -> list[tuple[str, Source]]:
    c: list[tuple[str, Source]] = [("solid", ("derived", _solid_marker))]

    def city(name: str, idx: int) -> None:
        c.append((name, ("city", idx)))

    # Sols
    for name, idx in [
        ("grass_a", 888),
        ("grass_b", 889),
        ("grass_dirty", 1018),
        ("dirt_a", 892),
        ("dirt_b", 893),
        ("dirt_grassy", 1008),
        ("gravel_a", 890),
        ("gravel_b", 891),
        ("rubble_ground", 896),
    ]:
        city(name, idx)
    c.append(("grass_dark_a", ("derived", _darker(888, 0.8))))  # sous-bois
    c.append(("grass_dark_b", ("derived", _darker(889, 0.8))))
    # Herbe sur terre (9 tranches) puis terre sur herbe (9 tranches)
    for prefix, base in [("gpatch", 925), ("dpatch", 935)]:
        for dy, row in enumerate(["n", "", "s"]):
            for dx, col in enumerate(["w", "", "e"]):
                part = (row + col) or "c"
                city(f"{prefix}_{part}", base + dy * 37 + dx)
    # Trottoirs
    for name, idx in [
        ("sidewalk", 741),
        ("sidewalk_b", 747),
        ("sidewalk_litter_a", 777),
        ("sidewalk_litter_b", 778),
    ]:
        city(name, idx)
    # Routes : ligne jaune sur le bord indiqué (n/s/e/w) ; passages piétons (sens de marche des piétons)
    for name, idx in [
        ("road", 714),
        ("road_line_n", 751),
        ("road_line_s", 717),
        ("road_line_e", 752),
        ("road_line_w", 788),
        ("road_xwalk_ns", 824),
        ("road_xwalk_ew", 827),
        ("road_manhole", 897),
        ("road_patch", 898),
    ]:
        city(name, idx)
    c.append(("road_weeds_a", ("derived", _green_pixels_onto(714, 1008))))
    c.append(("road_weeds_b", ("derived", _speckles_onto(714, 1008))))
    c.append(("sidewalk_weeds", ("derived", _green_pixels_onto(741, 1008))))
    # Toits plats (9 tranches + 2 détails) : rouge, gris, clair, beige
    for color, off in [("red", 0), ("grey", 8), ("light", 16), ("beige", 24)]:
        for part, idx in [
            ("nw", 0),
            ("n", 2),
            ("ne", 1),
            ("w", 3),
            ("c", 6),
            ("e", 40),
            ("sw", 37),
            ("s", 39),
            ("se", 38),
            ("vent", 43),
            ("hatch", 44),
        ]:
            city(f"roof_{color}_{part}", idx + off)
    # Façades (2 rangées : haut sans socle, bas avec socle) : brique rouge, grise, beige
    for color, off in [("red", 0), ("grey", 4), ("beige", 8)]:
        for part, idx in [
            ("top_w", 186),
            ("top_c", 187),
            ("top_e", 188),
            ("base_w", 297),
            ("base_c", 298),
            ("base_e", 299),
        ]:
            city(f"wall_{color}_{part}", idx + off)
    # Ouvertures (transparentes, posées dans `decor` sur une façade)
    for name, idx in [
        ("window", 767),
        ("window_broken", 770),
        ("window_small", 765),
        ("window_tall_broken", 733),
        ("door_glass", 800),
        ("door_glass_broken", 840),
        ("door_wood", 1019),
        ("door_wood_round", 982),
        ("door_dark", 841),
        ("door_wood_broken", 622),
    ]:
        city(name, idx)
    # Arbres : pied (tronc, solide) + cime (calque `above`)
    for name, top, base in [("dark", 403, 440), ("autumn", 402, 439), ("light", 401, 438)]:
        city(f"tree_{name}_top", top)
        city(f"tree_{name}_base", base)
    for name, idx in [("bush_dark", 514), ("bush_autumn", 513), ("bush_light", 512), ("planter_base", 477)]:
        city(name, idx)
    # Voitures : _h = 3x2 vue de côté, _v = 2x2 vue de face ; suffixe = ligne/colonne
    for color, h0, v0 in [("green", 623, 697), ("grey", 771, 845), ("orange", 919, 993)]:
        for dy in range(2):
            for dx in range(3):
                city(f"car_{color}_h_{dy}{dx}", h0 + dy * 37 + dx)
            for dx in range(2):
                city(f"car_{color}_v_{dy}{dx}", v0 + dy * 37 + dx)
    # Accessoires et débris
    for name, idx in [
        ("barrel_rust", 143),
        ("trash_can", 144),
        ("trash_full", 145),
        ("rubble", 493),
        ("debris", 494),
        ("tire", 495),
        ("bin_dark", 496),
        ("tires_stack", 532),
        ("hydrant", 533),
        ("crate", 605),
        ("boxes", 643),
        ("cone", 680),
        ("barricade_w", 209),
        ("barricade_e", 210),
    ]:
        city(name, idx)
    return c


def grade(img: Image.Image) -> Image.Image:
    out = img.copy()
    px = out.load()
    assert px is not None
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            if g > r + 20 and g > b:
                r = round(r + (g - r) * GRADE_DRY)
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            ch = []
            for v, t in zip((r, g, b), GRADE_TINT, strict=True):
                v2 = (v + (lum - v) * GRADE_DESATURATE) * GRADE_BRIGHTNESS * t
                ch.append(max(0, min(255, round(v2))))
            px[x, y] = (ch[0], ch[1], ch[2], a)
    return out


def build_tileset(ld: Loader) -> tuple[bytes, bytes]:
    entries = catalog()
    names = [n for n, _ in entries]
    if len(set(names)) != len(names):
        raise ValueError("noms de tuiles en double")
    rows = (len(entries) + TILESET_COLUMNS - 1) // TILESET_COLUMNS
    sheet = Image.new("RGBA", (TILESET_COLUMNS * TILE, rows * TILE), (0, 0, 0, 0))
    tiles: dict[str, int] = {}
    sources: dict[str, str] = {}
    coverage: dict[str, float] = {}
    for i, (name, (kind, ref)) in enumerate(entries):
        if kind == "derived":
            assert callable(ref)
            img = ref(ld)
            sources[name] = "dérivée"
        else:
            assert isinstance(ref, int)
            img = ld.city(ref) if kind == "city" else ld.tile(URBAN, ref)
            sources[name] = f"{kind}:{ref:04d}"
        if name != "solid":
            img = grade(img)
        alpha = img.getchannel("A")
        coverage[name] = round((TILE * TILE - alpha.histogram()[0]) / (TILE * TILE), 3)
        sheet.alpha_composite(img, ((i % TILESET_COLUMNS) * TILE, (i // TILESET_COLUMNS) * TILE))
        tiles[name] = i
    meta = {
        "_comment": "AUTO-GÉNÉRÉ par tools/assets/build_assets.py. Ne pas modifier.",
        "image": "valcendre.png",
        "tilewidth": TILE,
        "tileheight": TILE,
        "columns": TILESET_COLUMNS,
        "tilecount": len(entries),
        "tiles": tiles,
        "sources": sources,
        "coverage": coverage,
    }
    return _png_bytes(sheet), _json_bytes(meta)


# --- Personnages (RPG Urban Pack) -----------------------------------------------------------------
# Chaque personnage occupe 4 colonnes x 3 lignes : colonnes = gauche, face (bas), dos (haut), droite ;
# lignes = immobile, marche A, marche B. Vérifié visuellement sur la planche.
CHAR_COL0 = 23
CHAR_SRC_COL = {"down": 1, "left": 0, "right": 3, "up": 2}
DIRECTIONS = ["down", "left", "right", "up"]
CHARACTERS = {
    "survivor": (15, "femme brune au bandeau, veste ocre"),
    "survivor_b": (12, "homme chauve, t-shirt gris"),
    "survivor_c": (9, "ouvrier au casque de chantier"),
    "survivor_d": (6, "vieil homme barbu aux cheveux gris"),
}
WALK_FPS = 8
RUN_FPS = 12


# --- Zombies : personnages du RPG Urban Pack recolorés (dérivés CC0) -------------------------------
# Peau verdâtre et livide, vêtements délavés et salis, quelques taches sombres.
ZOMBIES = {
    "zombie_rodeur": (3, "rôdeur : ancien employé en chemise orange, peau livide"),
}


def _zombify(img: Image.Image) -> Image.Image:
    out = img.copy()
    px = out.load()
    assert px is not None
    for y in range(TILE):
        for x in range(TILE):
            r, g, b, a = px[x, y]
            if not a:
                continue
            lum = (r * 299 + g * 587 + b * 114) // 1000
            if r > g > b and r - b > 50 and lum > 150:
                # Peau : vert-de-gris livide.
                px[x, y] = (int(lum * 0.62), int(lum * 0.82), int(lum * 0.55), a)
            else:
                # Vêtements, cheveux : désaturés et assombris, léger virage boueux.
                gray = lum * 0.55
                px[x, y] = (
                    int(gray + (r - lum) * 0.35 + 6),
                    int(gray + (g - lum) * 0.35 + 4),
                    int(gray + (b - lum) * 0.35),
                    a,
                )
    # Taches de sang séché, à des positions fixes (déterministe) sur le torse.
    for x, y in ((6, 9), (9, 10), (7, 11)):
        r, g, b, a = px[x, y]
        if a:
            px[x, y] = (92, 22, 20, a)
    return out


def build_character(
    ld: Loader, name: str, row0: int, desc: str, recolor: Callable[[Image.Image], Image.Image] | None = None
) -> tuple[bytes, bytes]:
    sheet = Image.new("RGBA", (3 * TILE, 4 * TILE), (0, 0, 0, 0))
    src_ids: list[int] = []
    for r, direction in enumerate(DIRECTIONS):
        for f in range(3):
            idx = (row0 + f) * URBAN_COLUMNS + CHAR_COL0 + CHAR_SRC_COL[direction]
            src_ids.append(idx)
            tile = ld.tile(URBAN, idx)
            sheet.alpha_composite(recolor(tile) if recolor else tile, (f * TILE, r * TILE))
    anims: dict[str, dict[str, object]] = {}
    for r, direction in enumerate(DIRECTIONS):
        stand, a, b = r * 3, r * 3 + 1, r * 3 + 2
        anims[f"idle_{direction}"] = {"frames": [stand], "fps": 1, "loop": True}
        anims[f"walk_{direction}"] = {"frames": [a, stand, b, stand], "fps": WALK_FPS, "loop": True}
        anims[f"run_{direction}"] = {"frames": [a, stand, b, stand], "fps": RUN_FPS, "loop": True}
    meta = {
        "_comment": "AUTO-GÉNÉRÉ par tools/assets/build_assets.py. Ne pas modifier.",
        "image": f"{name}.png",
        "description": desc,
        "frameWidth": TILE,
        "frameHeight": TILE,
        "columns": 3,
        "rows": 4,
        "frameOrder": "index = ligne * 3 + colonne ; ligne = direction (down, left, right, up), "
        "colonne = image (0 immobile, 1 marche A, 2 marche B)",
        "directions": DIRECTIONS,
        "animations": anims,
        "fps": {"idle": 1, "walk": WALK_FPS, "run": RUN_FPS},
        "anchor": {"x": 0.5, "y": 0.5},
        "source": {"pack": "Kenney RPG Urban Pack (CC0)", "tiles": src_ids},
    }
    return _png_bytes(sheet), _json_bytes(meta)


def _png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _json_bytes(data: object) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


# Objet au sol : carton ouvert du RPG Urban Pack.
LOOT_TILE = 274


def outputs(src: Path) -> dict[Path, bytes]:
    ld = Loader(src)
    png, meta = build_tileset(ld)
    out = {TILESET_PNG: png, TILESET_JSON: meta}
    for name, (row0, desc) in CHARACTERS.items():
        png, meta = build_character(ld, name, row0, desc)
        out[SPRITES_DIR / f"{name}.png"] = png
        out[SPRITES_DIR / f"{name}.json"] = meta
    for name, (row0, desc) in ZOMBIES.items():
        png, meta = build_character(ld, name, row0, desc, _zombify)
        out[SPRITES_DIR / f"{name}.png"] = png
        out[SPRITES_DIR / f"{name}.json"] = meta
    out[SPRITES_DIR / "loot.png"] = _png_bytes(ld.tile(URBAN, LOOT_TILE))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "src", nargs="?", type=Path, default=DEFAULT_SRC, help="dossier `2d` des packs Kenney"
    )
    parser.add_argument("--check", action="store_true", help="vérifie que les sorties sont à jour")
    args = parser.parse_args()
    files = outputs(args.src.resolve())
    if args.check:
        stale = [p for p, data in files.items() if not p.exists() or p.read_bytes() != data]
        for p in stale:
            print(f"pas à jour : {p.relative_to(ROOT)}", file=sys.stderr)
        return 1 if stale else 0
    for path, data in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        print(f"écrit {path.relative_to(ROOT)} ({len(data)} octets)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
