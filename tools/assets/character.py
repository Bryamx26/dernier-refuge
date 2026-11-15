"""Personnage modulaire « poupée de papier » : corps de base + pièces équipables.

Création originale du projet (aucun asset externe) : tout est dessiné par ce script, de façon
déterministe. Un personnage est un empilement de calques de même taille (24 × 32 px) :

    corps (sexe, couleur de peau) < pantalon < veste < cheveux < couvre-chef < sac à dos

Le corps est décrit par des grilles de « régions » (tête, torse, bras, jambes...). Les vêtements
ne sont pas dessinés à la main : ils sont calculés à partir des régions du corps (le pantalon
recouvre les jambes, la veste le torse et les bras, etc.). Quand le corps sera animé, les
vêtements suivront donc automatiquement chaque pose.

Planche d'un calque : 4 cadres côte à côte, dans l'ordre DIRECTIONS (bas, gauche, droite, haut).
"""

from __future__ import annotations

from PIL import Image

FRAME_W, FRAME_H = 24, 32
OFF_X, OFF_Y = 5, 3
GRID_W = 14
DIRECTIONS = ("down", "left", "right", "up")

RGBA = tuple[int, int, int, int]
Pixels = dict[tuple[int, int], RGBA]

# --------------------------------------------------------------------------- corps (régions)
# h tête · e œil · k cou · t torse · c poitrine (sous-vêtement haut) · a/b bras · n main
# u bassin (sous-vêtement) · l/m jambes · f pied.  Ligne 0 : réservée aux couvre-chefs.
_FRONT_M = """
..............
....hhhhhh....
...hhhhhhhh...
...hhhhhhhh...
...hhehhehh...
...hhhhhhhh...
...hhhhhhhh...
....hhhhhh....
.....kkkk.....
..attttttttb..
.aattttttttbb.
.aattttttttbb.
.aattttttttbb.
.aattttttttbb.
.aattttttttbb.
.nnuuuuuuuunn.
.nnuuuuuuuunn.
...llllmmmm...
...llllmmmm...
...lll..mmm...
...lll..mmm...
...lll..mmm...
...lll..mmm...
...lll..mmm...
...lll..mmm...
...lll..mmm...
..ffff..ffff..
"""

_FRONT_F = """
..............
....hhhhhh....
...hhhhhhhh...
...hhhhhhhh...
...hhehhehh...
...hhhhhhhh...
...hhhhhhhh...
....hhhhhh....
.....kkkk.....
...tttttttt...
.aaccccccccbb.
.aaccccccccbb.
.aa.tttttt.bb.
.aa.tttttt.bb.
.aattttttttbb.
.nnuuuuuuuunn.
.nnuuuuuuuunn.
...llllmmmm...
...llllmmmm...
...lll..mmm...
...lll..mmm...
...lll..mmm...
...lll..mmm...
...lll..mmm...
...lll..mmm...
...lll..mmm...
..ffff..ffff..
"""

_SIDE_M = """
..............
....hhhhhh....
...hhhhhhhh...
...hhhhhhhh...
...hhhhhheh...
...hhhhhhhhh..
...hhhhhhhh...
....hhhhhh....
.....kkk......
....tttttt....
....ttaatt....
....ttaatt....
....ttaatt....
....ttaatt....
....ttaatt....
....uunnuu....
....uunnuu....
....mlllll....
....mlllll....
.....mlll.....
.....mlll.....
.....mlll.....
.....mlll.....
.....mlll.....
.....mlll.....
.....mlll.....
.....fffff....
"""

_SIDE_F = """
..............
....hhhhhh....
...hhhhhhhh...
...hhhhhhhh...
...hhhhhheh...
...hhhhhhhhh..
...hhhhhhhh...
....hhhhhh....
.....kkk......
....tttttt....
....ccaaccc...
....ccaaccc...
.....taatt....
.....taatt....
....ttaatt....
....uunnuu....
....uunnuu....
....mlllll....
....mlllll....
.....mlll.....
.....mlll.....
.....mlll.....
.....mlll.....
.....mlll.....
.....mlll.....
.....mlll.....
.....fffff....
"""


def _rows(text: str) -> list[str]:
    rows = [r for r in text.strip("\n").split("\n")]
    assert all(len(r) == GRID_W for r in rows), [len(r) for r in rows]
    return rows


def _mirror(rows: list[str]) -> list[str]:
    swap = str.maketrans("ab", "ba")
    return [r[::-1].translate(swap) for r in rows]


def body_grid(sex: str, direction: str) -> list[str]:
    front = _rows(_FRONT_M if sex == "m" else _FRONT_F)
    side = _rows(_SIDE_M if sex == "m" else _SIDE_F)
    if direction == "down":
        return front
    if direction == "up":
        return [r.replace("e", "h") for r in front]
    return side if direction == "right" else _mirror(side)


def _regions(rows: list[str]) -> dict[tuple[int, int], str]:
    return {(x, y): ch for y, r in enumerate(rows) for x, ch in enumerate(r) if ch != "."}


# --------------------------------------------------------------------------- couleurs
def _mul(c: tuple[int, int, int], k: float) -> RGBA:
    return (min(255, round(c[0] * k)), min(255, round(c[1] * k)), min(255, round(c[2] * k)), 255)


SKINS = {
    "claire": (244, 205, 170),
    "mate": (214, 164, 120),
    "brune": (160, 108, 72),
    "noire": (104, 68, 48),
}
HAIR_COLORS = {
    "noir": (44, 38, 40),
    "brun": (98, 62, 36),
    "blond": (214, 176, 92),
    "roux": (176, 78, 36),
}
UNDERWEAR = (86, 96, 110)
EYE = (30, 24, 28, 255)

CLOTHES = {
    "veste": (92, 104, 68),  # kaki
    "pantalon": (62, 78, 112),  # jean
    "chaussures": (58, 44, 36),
    "casque": (78, 92, 70),
    "casquette": (150, 54, 46),
    "sac": (120, 92, 56),
    "combi": (206, 204, 190),  # combinaison de protection, gris clair
    "combi_bande": (226, 126, 40),
    "combi_bottes": (60, 62, 68),
    "combi_verre": (96, 196, 190),
    "combi_filtre": (52, 54, 60),
}


# --------------------------------------------------------------------------- rendu d'un calque
def _shade(pixels: dict[tuple[int, int], tuple[int, int, int]], light: float = 1.0) -> Pixels:
    """Ombrage simple, lumière en haut à gauche : bord droit et bas plus sombres."""
    out: Pixels = {}
    for (x, y), c in pixels.items():
        k = light
        if (x + 1, y) not in pixels:
            k *= 0.84
        if (x, y + 1) not in pixels:
            k *= 0.88
        out[(x, y)] = _mul(c, k)
    return out


def _outline(pixels: Pixels, body: set[tuple[int, int]], color: RGBA) -> Pixels:
    """Contour extérieur : uniquement hors du calque ET hors de la silhouette du corps."""
    out = dict(pixels)
    for x, y in list(pixels):
        for p in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if p not in pixels and p not in body:
                out[p] = color
    return out


def _frame(pixels: Pixels) -> Image.Image:
    img = Image.new("RGBA", (FRAME_W, FRAME_H), (0, 0, 0, 0))
    for (x, y), c in pixels.items():
        px, py = x + OFF_X, y + OFF_Y
        if 0 <= px < FRAME_W and 0 <= py < FRAME_H:
            img.putpixel((px, py), c)
    return img


def _rows_of(reg: dict[tuple[int, int], str], chars: str) -> list[int]:
    return sorted({y for (x, y), ch in reg.items() if ch in chars})


# --------------------------------------------------------------------------- calques
def layer_body(reg, direction: str, skin: tuple[int, int, int]) -> Pixels:
    flat: dict[tuple[int, int], tuple[int, int, int]] = {}
    for p, ch in reg.items():
        if ch in "uc":
            flat[p] = UNDERWEAR
        elif ch in "ab":
            flat[p] = _mul(skin, 0.9)[:3]
        elif ch in "km":
            flat[p] = _mul(skin, 0.86)[:3]
        else:
            flat[p] = skin
    px = _shade(flat)
    for p, ch in reg.items():
        if ch == "e":
            px[p] = EYE
    return _outline(px, set(), _mul(skin, 0.36))


def layer_pants(reg, direction: str, color, shoes, boots_rows: int = 0) -> Pixels:
    legs = _rows_of(reg, "lm")
    last = legs[-1]
    flat = {}
    for p, ch in reg.items():
        if ch in "ulm":
            flat[p] = _mul(color, 0.9)[:3] if ch == "m" else color
            if boots_rows and p[1] > last - boots_rows:
                flat[p] = shoes
        elif ch == "f":
            flat[p] = shoes
    px = _shade(flat)
    belt = _rows_of(reg, "u")[0]
    for p, ch in reg.items():
        if ch == "u" and p[1] == belt:
            px[p] = _mul(color, 0.62)
    return _outline(px, set(reg), _mul(color, 0.4))


def layer_jacket(reg, direction: str, color, detail: str = "zip", gloves=None) -> Pixels:
    torso_rows = _rows_of(reg, "tc")
    flat = {}
    for p, ch in reg.items():
        if ch in "tc":
            flat[p] = color
        elif ch in "ab":
            flat[p] = _mul(color, 0.86)[:3]
    # La veste est ample : on comble les creux de la taille entre les bras.
    for y in torso_rows:
        xs = [x for (x, yy) in flat if yy == y]
        for x in range(min(xs), max(xs) + 1):
            flat.setdefault((x, y), color)
    hem = _rows_of(reg, "u")[0]
    for p, ch in reg.items():
        if ch == "u" and p[1] == hem:
            flat[p] = color
        if gloves and ch == "n":
            flat[p] = gloves
    px = _shade(flat)
    for p, ch in reg.items():
        if ch == "k":
            px[p] = _mul(color, 0.7)  # col
        if ch == "u" and p[1] == hem:
            px[p] = _mul(color, 0.7)  # ourlet
    if detail == "zip" and direction == "down":
        cx = (min(x for x, _ in reg) + max(x for x, _ in reg)) // 2 + 1
        for y in torso_rows:
            px[(cx, y)] = _mul(color, 0.66)
    if detail == "band":
        y = torso_rows[2]
        for p, ch in reg.items():
            if p[1] == y and ch in "ab":
                px[p] = _mul(CLOTHES["combi_bande"], 1.0)
    return _outline(px, set(reg), _mul(color, 0.4))


def _stamp(text: str, direction: str) -> dict[tuple[int, int], str]:
    """Grille d'un accessoire (cheveux, couvre-chef, sac) ; « left » = miroir de « right »."""
    rows = _rows(text)
    if direction == "left":
        rows = [r[::-1] for r in rows]
    return {(x, y): ch for y, r in enumerate(rows) for x, ch in enumerate(r) if ch != "."}


def _stamped(grids: dict[str, str], direction: str, palette: dict[str, tuple[int, int, int]], reg, outline) -> Pixels:
    key = "side" if direction in ("left", "right") else direction
    cells = _stamp(grids[key], direction)
    main = {p: palette[ch] for p, ch in cells.items() if ch.isupper()}
    px = _shade(main)
    for p, ch in cells.items():
        if ch.islower():  # détails sans ombrage (visière, sangles, verre...)
            px[p] = (*palette[ch], 255)
    return _outline(px, set(reg), outline)


_E = ".............."

HAIR = {
    "court": {
        "down": "\n".join(["....HHHHHH....", "...HHHHHHHH...", "...HHHHHHHH...", "...HH....HH...", "...H......H..."] + [_E] * 22),
        "side": "\n".join(["....HHHHHH....", "...HHHHHHHH...", "...HHHHHHHH...", "...HHHHHH.....", "...HHHH.......", "...HHH........"] + [_E] * 21),
        "up": "\n".join(["....HHHHHH....", "...HHHHHHHH...", "...HHHHHHHH...", "...HHHHHHHH...", "...HHHHHHHH...", "...HHHHHHHH...", "....HHHHHH...."] + [_E] * 20),
    },
    "long": {
        "down": "\n".join(["....HHHHHH....", "...HHHHHHHH...", "..HHHHHHHHHH..", "..HHH....HHH..", "..HH......HH..", "..HH......HH..", "..HH......HH..", "..HH......HH..", "..HH......HH..", "..HH......HH..", "..H........H.."] + [_E] * 16),
        "side": "\n".join(["....HHHHHH....", "...HHHHHHHH...", "..HHHHHHHHH...", "..HHHHHHH.....", "..HHHHH.......", "..HHHH........", "..HHHH........", "..HHHH........", "..HHHH........", "..HHH.........", "..HH.........."] + [_E] * 16),
        "up": "\n".join(["....HHHHHH....", "...HHHHHHHH...", "..HHHHHHHHHH..", "..HHHHHHHHHH..", "..HHHHHHHHHH..", "..HHHHHHHHHH..", "..HHHHHHHHHH..", "..HHHHHHHHHH..", "..HHHHHHHHHH..", "..HHHHHHHHHH..", "...HHHHHHHH..."] + [_E] * 16),
    },
}

HELMET = {
    "down": "\n".join(["...XXXXXXXX...", "..XXXXXXXXXX..", "..XXXXXXXXXX..", "..xxxxxxxxxx.."] + [_E] * 23),
    "side": "\n".join(["...XXXXXXXX...", "..XXXXXXXXXX..", "..XXXXXXXXXX..", "..xxxxxxxxxxx.", "..XXX........."] + [_E] * 22),
    "up": "\n".join(["...XXXXXXXX...", "..XXXXXXXXXX..", "..XXXXXXXXXX..", "..XXXXXXXXXX..", "..xxxxxxxxxx.."] + [_E] * 22),
}

CAP = {
    "down": "\n".join(["....XXXXXX....", "...XXXXXXXX...", "...XXXXXXXX...", "..xxxxxxxxxx.."] + [_E] * 23),
    "side": "\n".join(["....XXXXXX....", "...XXXXXXXX...", "...XXXXXXXX...", "...XXXXXxxxxx."] + [_E] * 23),
    "up": "\n".join(["....XXXXXX....", "...XXXXXXXX...", "...XXXXXXXX...", "...XXXXXXXX...", "....xxxxxx...."] + [_E] * 22),
}

# Capuche de la combinaison : G verre du masque, f cartouche filtrante.
HOOD = {
    "down": "\n".join(["...XXXXXXXX...", "..XXXXXXXXXX..", "..XXXXXXXXXX..", "..XXggggggXX..", "..XXggggggXX..", "..XXggggggXX..", "..XXXXffXXXX..", "...XXXffXXX...", "....XXXXXX...."] + [_E] * 18),
    "side": "\n".join(["...XXXXXXXX...", "..XXXXXXXXXX..", "..XXXXXXXXXX..", "..XXXXXXgggg..", "..XXXXXXgggg..", "..XXXXXXgggg..", "..XXXXXXXXfff.", "...XXXXXXXfff.", "....XXXXXX...."] + [_E] * 18),
    "up": "\n".join(["...XXXXXXXX...", "..XXXXXXXXXX..", "..XXXXXXXXXX..", "..XXXXXXXXXX..", "..XXXXXXXXXX..", "..XXXXXXXXXX..", "..XXXXXXXXXX..", "...XXXXXXXX...", "....XXXXXX...."] + [_E] * 18),
}

# Sac à dos : B corps du sac, s sangles / rabat.
PACK = {
    "down": "\n".join([_E] * 9 + ["....s....s....", "....s....s....", "....s....s....", "....s....s....", "....s....s...."] + [_E] * 13),
    "side": "\n".join([_E] * 9 + [".BBBs.........", ".BBBBs........", ".ssss.s.......", ".BBBB.s.......", ".BBBBs........", ".BBBs.........", ".BBB.........."] + [_E] * 11),
    "up": "\n".join([_E] * 8 + ["....ssssss....", "...BBBBBBBB...", "...BBBBBBBB...", "...ssssssss...", "...BBBBBBBB...", "...BBsssBBB...", "...BBBBBBBB...", "...BBBBBBBB..."] + [_E] * 11),
}


def layer_hair(reg, direction, style: str, color) -> Pixels:
    return _stamped(HAIR[style], direction, {"H": color}, reg, _mul(color, 0.5))


def layer_helmet(reg, direction) -> Pixels:
    c = CLOTHES["casque"]
    return _stamped(HELMET, direction, {"X": c, "x": _mul(c, 0.62)[:3]}, reg, _mul(c, 0.4))


def layer_cap(reg, direction) -> Pixels:
    c = CLOTHES["casquette"]
    return _stamped(CAP, direction, {"X": c, "x": _mul(c, 0.66)[:3]}, reg, _mul(c, 0.4))


def layer_hood(reg, direction) -> Pixels:
    c = CLOTHES["combi"]
    pal = {"X": c, "g": CLOTHES["combi_verre"], "f": CLOTHES["combi_filtre"]}
    return _stamped(HOOD, direction, pal, reg, _mul(c, 0.4))


def layer_pack(reg, direction) -> Pixels:
    c = CLOTHES["sac"]
    return _stamped(PACK, direction, {"B": c, "s": _mul(c, 0.6)[:3]}, reg, _mul(c, 0.4))


# Pièces équipables : nom → (emplacement, fonction(reg, direction) → pixels)
PIECES = {
    "pantalon_jean": ("pantalon", lambda r, d: layer_pants(r, d, CLOTHES["pantalon"], CLOTHES["chaussures"])),
    "veste_kaki": ("veste", lambda r, d: layer_jacket(r, d, CLOTHES["veste"])),
    "casque_militaire": ("tete", layer_helmet),
    "casquette_rouge": ("tete", layer_cap),
    "sac_a_dos": ("dos", layer_pack),
    "combi_capuche": ("tete", layer_hood),
    "combi_haut": ("veste", lambda r, d: layer_jacket(r, d, CLOTHES["combi"], "band", CLOTHES["combi_bottes"])),
    "combi_bas": ("pantalon", lambda r, d: layer_pants(r, d, CLOTHES["combi"], CLOTHES["combi_bottes"], 3)),
}
SLOT_ORDER = ("pantalon", "veste", "cheveux", "tete", "dos")  # du dessous vers le dessus


def sheet(build) -> Image.Image:
    """Planche 4 directions d'un calque ; `build(direction)` renvoie les pixels."""
    out = Image.new("RGBA", (FRAME_W * 4, FRAME_H), (0, 0, 0, 0))
    for i, d in enumerate(DIRECTIONS):
        out.alpha_composite(_frame(build(d)), (i * FRAME_W, 0))
    return out


def body_sheet(sex: str, skin: str) -> Image.Image:
    return sheet(lambda d: layer_body(_regions(body_grid(sex, d)), d, SKINS[skin]))


def hair_sheet(sex: str, style: str, color: str) -> Image.Image:
    return sheet(lambda d: layer_hair(_regions(body_grid(sex, d)), d, style, HAIR_COLORS[color]))


def piece_sheet(sex: str, name: str) -> Image.Image:
    fn = PIECES[name][1]
    return sheet(lambda d: fn(_regions(body_grid(sex, d)), d))


def assemble(sex: str, skin: str, hair: tuple[str, str] | None, pieces: list[str]) -> Image.Image:
    """Empile les calques dans l'ordre des emplacements (comme le fera le client)."""
    out = body_sheet(sex, skin)
    by_slot: dict[str, Image.Image] = {}
    if hair:
        by_slot["cheveux"] = hair_sheet(sex, *hair)
    for name in pieces:
        by_slot[PIECES[name][0]] = piece_sheet(sex, name)
    if "combi_capuche" in pieces:
        by_slot.pop("cheveux", None)  # la capuche enferme les cheveux
    for slot in SLOT_ORDER:
        if slot in by_slot:
            out.alpha_composite(by_slot[slot])
    return out


def main() -> None:
    """Écrit tous les calques dans assets/sprites/character/ (sorties versionnées)."""
    from pathlib import Path

    out = Path(__file__).resolve().parents[2] / "assets" / "sprites" / "character"
    out.mkdir(parents=True, exist_ok=True)
    for sex in "mf":
        for skin in SKINS:
            body_sheet(sex, skin).save(out / f"corps_{sex}_{skin}.png")
        for style in HAIR:
            for color in HAIR_COLORS:
                hair_sheet(sex, style, color).save(out / f"cheveux_{style}_{color}.png")  # identique m/f
        for name in PIECES:
            piece_sheet(sex, name).save(out / f"{name}_{sex}.png")


if __name__ == "__main__":
    main()
