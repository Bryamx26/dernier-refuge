"""Génération des planches d'animation des personnages (dérivées des sprites Kenney CC0).

Chaque personnage de base fournit 3 images 16 px par direction (immobile, pas A, pas B).
Ce module en dérive, par code et de façon déterministe, toutes les animations du jeu dans des
cadres 24 × 24 (marge pour les armes, la chute, etc.). Les armes, poings, éclairs et flaques
sont dessinés pixel par pixel ; aucune image externe n'est ajoutée.

Planche : 4 colonnes (images) ; une ligne par (animation, direction), dans l'ordre de ANIMS
puis de DIRECTIONS. Index Phaser = ligne * 4 + colonne.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PIL import Image

BASE = 16
FRAME = 24
COLUMNS = 4
OFF_X, OFF_Y = 4, 6  # position du cadre 16 px dans le cadre 24 px
DIRECTIONS = ("down", "left", "right", "up")
VEC = {"down": (0, 1), "left": (-1, 0), "right": (1, 0), "up": (0, -1)}
ANGLE = {"down": 90.0, "left": 180.0, "right": 0.0, "up": -90.0}
# Main « active » dans le cadre 24 px (déduite des sprites Kenney : mains en x=2/13, y=12).
HAND = {"down": (17, 18), "left": (8, 18), "right": (15, 18), "up": (6, 17)}

OUTLINE = (40, 26, 22, 255)
STEEL = (200, 204, 210, 255)
GUNMETAL = (52, 52, 58, 255)
WOOD = (138, 90, 43, 255)
WOOD_DARK = (107, 68, 38, 255)
FLASH = (255, 224, 138, 255)
FLASH_CORE = (255, 246, 200, 255)
SHELL = (178, 40, 32, 255)
BRASS = (214, 170, 72, 255)
BLOOD = (110, 18, 18, 255)
BLOOD_DARK = (74, 10, 10, 255)


@dataclass(frozen=True)
class Anim:
    name: str
    frames: int
    fps: int
    loop: bool


SURVIVOR_ANIMS = (
    Anim("idle", 2, 2, True),
    Anim("walk", 4, 8, True),
    Anim("run", 4, 12, True),
    Anim("attack_fists", 3, 12, False),
    Anim("attack_knife", 3, 12, False),
    Anim("attack_bat", 4, 12, False),
    Anim("shoot_pistol", 2, 14, False),
    Anim("shoot_shotgun", 3, 10, False),
    Anim("reload_pistol", 3, 4, True),
    Anim("reload_shotgun", 4, 5, True),
    Anim("search", 4, 6, True),
    Anim("hurt", 2, 10, False),
    Anim("death", 4, 8, False),
)

ZOMBIE_ANIMS = (
    Anim("idle", 2, 2, True),
    Anim("walk", 4, 5, True),
    Anim("run", 4, 9, True),
    Anim("attack", 3, 8, False),
    Anim("hurt", 2, 10, False),
    Anim("death", 4, 8, False),
)


# --------------------------------------------------------------------------- outils pixels
def _canvas() -> Image.Image:
    return Image.new("RGBA", (FRAME, FRAME), (0, 0, 0, 0))


def _place(base: Image.Image, dx: int = 0, dy: int = 0) -> Image.Image:
    c = _canvas()
    c.alpha_composite(base, (OFF_X + dx, OFF_Y + dy))
    return c


def _put(img: Image.Image, x: int, y: int, color: tuple[int, int, int, int]) -> None:
    if 0 <= x < img.width and 0 <= y < img.height:
        img.putpixel((x, y), color)


def _line(layer: Image.Image, x0: float, y0: float, angle_deg: float, length: int, color) -> tuple[int, int]:
    """Trace un segment de `length` pixels ; renvoie le dernier point."""
    a = math.radians(angle_deg)
    x = y = 0
    for i in range(length):
        x = round(x0 + math.cos(a) * i)
        y = round(y0 + math.sin(a) * i)
        _put(layer, x, y, color)
    return x, y


def _outlined(layer: Image.Image) -> Image.Image:
    """Ajoute un contour sombre d'un pixel autour des pixels opaques du calque."""
    out = layer.copy()
    px = layer.load()
    for y in range(layer.height):
        for x in range(layer.width):
            if px[x, y][3]:
                continue
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if 0 <= nx < layer.width and 0 <= ny < layer.height and px[nx, ny][3]:
                    out.putpixel((x, y), OUTLINE)
                    break
    return out


def _skin(base: Image.Image) -> tuple[int, int, int, int]:
    """Couleur de peau : pixel le plus fréquent du visage (zone centrale de la tête)."""
    counts: dict[tuple[int, int, int, int], int] = {}
    for y in range(5, 9):
        for x in range(5, 11):
            p = base.getpixel((x, y))
            if p[3] and sum(p[:3]) > 250:
                counts[p] = counts.get(p, 0) + 1
    return max(counts, key=lambda k: counts[k]) if counts else (230, 180, 140, 255)


def _tint(img: Image.Image, rgb: tuple[int, int, int], amount: float) -> Image.Image:
    out = img.copy()
    px = out.load()
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = px[x, y]
            if a:
                px[x, y] = (
                    round(r + (rgb[0] - r) * amount),
                    round(g + (rgb[1] - g) * amount),
                    round(b + (rgb[2] - b) * amount),
                    a,
                )
    return out


def _crouch(base: Image.Image) -> Image.Image:
    """Accroupi : le haut du corps descend de 2 px sur les jambes (lignes 14-15 masquées)."""
    out = Image.new("RGBA", base.size, (0, 0, 0, 0))
    out.alpha_composite(base.crop((0, 14, BASE, BASE)), (0, 14))
    out.alpha_composite(base.crop((0, 0, BASE, 14)), (0, 2))
    return out


def _breathe(base: Image.Image) -> Image.Image:
    """Respiration : la tête (lignes 0-9) descend d'un pixel."""
    out = base.copy()
    head = base.crop((0, 0, BASE, 10))
    for y in range(0, 10):
        for x in range(BASE):
            out.putpixel((x, y), (0, 0, 0, 0))
    out.alpha_composite(head, (0, 1))
    return out


def _sway(base: Image.Image, dx: int) -> Image.Image:
    """Balancement : la tête (lignes 0-9) se décale de dx pixels."""
    out = base.copy()
    head = base.crop((0, 0, BASE, 10))
    for y in range(0, 10):
        for x in range(BASE):
            out.putpixel((x, y), (0, 0, 0, 0))
    out.alpha_composite(head, (dx, 0))
    return out


def _compose(body: Image.Image, item: Image.Image | None, behind: bool) -> Image.Image:
    if item is None:
        return body
    item = _outlined(item)
    out = _canvas()
    if behind:
        out.alpha_composite(item)
        out.alpha_composite(body)
    else:
        out.alpha_composite(body)
        out.alpha_composite(item)
    return out


# --------------------------------------------------------------------------- poses
def _fist(layer: Image.Image, x: int, y: int, skin) -> None:
    for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
        _put(layer, x + dx - 1, y + dy - 1, skin)


def _held(d: str, base: Image.Image, skin, draw, shift: tuple[int, int] = (0, 0)) -> Image.Image:
    """Corps décalé de `shift` + objet tenu dessiné par `draw(layer, hx, hy, angle)`."""
    body = _place(base, *shift)
    layer = _canvas()
    hx, hy = HAND[d]
    draw(layer, hx + shift[0], hy + shift[1], ANGLE[d])
    return _compose(body, layer, behind=(d == "up"))


def _attack_melee(d: str, base: Image.Image, skin, blade: int) -> list[Image.Image]:
    vx, vy = VEC[d]
    frames = []
    for reach, lean in ((-1, (-vx, -vy)), (3, (vx, vy)), (1, (0, 0))):
        def draw(layer, hx, hy, ang, reach=reach):
            fx, fy = hx + vx * reach, hy + vy * reach
            if blade:
                _line(layer, fx + vx, fy + vy, ang, blade, STEEL)
            _fist(layer, fx, fy, skin)
        frames.append(_held(d, base, skin, draw, lean))
    return frames


def _attack_bat(d: str, base: Image.Image, skin) -> list[Image.Image]:
    vx, vy = VEC[d]
    frames = []
    # Armé derrière l'épaule, puis balayage en arc devant soi.
    for rel, lean in ((-120, (-vx, -vy)), (-55, (0, 0)), (0, (vx, vy)), (55, (vx, vy))):
        def draw(layer, hx, hy, ang, rel=rel):
            a = ang + rel
            ex, ey = _line(layer, hx, hy, a, 9, WOOD)
            _line(layer, hx, hy, a, 3, WOOD_DARK)  # poignée
            _put(layer, ex, ey, WOOD_DARK)
            _fist(layer, hx, hy, skin)
        frames.append(_held(d, base, skin, draw, lean))
    return frames


def _gun(layer, hx, hy, ang, length: int, stock: int, metal) -> tuple[int, int]:
    if stock:
        _line(layer, hx, hy, ang + 180, stock + 1, WOOD)
    return _line(layer, hx, hy, ang, length, metal)


def _flash(layer, x, y, ang) -> None:
    a = math.radians(ang)
    fx, fy = round(x + math.cos(a)), round(y + math.sin(a))
    _put(layer, fx, fy, FLASH_CORE)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        _put(layer, fx + dx, fy + dy, FLASH)


def _shoot(d: str, base: Image.Image, skin, shotgun: bool) -> list[Image.Image]:
    vx, vy = VEC[d]
    length, stock = (7, 2) if shotgun else (4, 0)
    metal = GUNMETAL

    def aim(layer, hx, hy, ang):
        _gun(layer, hx, hy, ang, length, stock, metal)
        _fist(layer, hx, hy, skin)

    def fire(layer, hx, hy, ang):
        ex, ey = _gun(layer, hx, hy, ang, length, stock, metal)
        _flash(layer, ex, ey, ang)
        _fist(layer, hx, hy, skin)

    def pump(layer, hx, hy, ang):
        ex, ey = _gun(layer, hx, hy, ang, length, stock, metal)
        a = math.radians(ang)
        _put(layer, round(hx + math.cos(a) * 3), round(hy + math.sin(a) * 3), WOOD_DARK)
        _put(layer, round(ex + math.cos(a + 1.6) * 2), round(ey + math.sin(a + 1.6) * 2), SHELL)
        _fist(layer, hx, hy, skin)

    frames = [_held(d, base, skin, aim), _held(d, base, skin, fire, (-vx, -vy))]
    if shotgun:
        frames.append(_held(d, base, skin, pump))
    return frames


def _reload(d: str, base: Image.Image, skin, shotgun: bool) -> list[Image.Image]:
    """Arme abaissée (45° vers le bas), munition qui approche de l'arme."""
    length, stock = (7, 2) if shotgun else (4, 0)
    steps = (6, 4, 2, 0) if shotgun else (5, 2, 0)
    frames = []
    for k, dist in enumerate(steps):
        def draw(layer, hx, hy, ang, dist=dist, k=k):
            low = ang + (45 if ang in (0.0, 90.0) else -45)
            a = math.radians(low)
            _gun(layer, hx, hy, low, length, stock, GUNMETAL)
            mx, my = round(hx + math.cos(a) * 2), round(hy + math.sin(a) * 2)
            if shotgun:
                _put(layer, mx, my + dist, SHELL)
                _put(layer, mx, my + dist + 1, BRASS)
            else:
                _put(layer, mx, my + 1 + dist, GUNMETAL if k else BRASS)
            _fist(layer, hx, hy, skin)
        frames.append(_held(d, base, skin, draw))
    return frames


def _search(d: str, base: Image.Image, skin) -> list[Image.Image]:
    vx, vy = VEC[d]
    px, py = -vy, vx  # perpendiculaire
    low = _crouch(base)
    frames = []
    for side in (0, 1, -1, 1):
        def draw(layer, hx, hy, ang, side=side):
            fx = hx + vx * 2 + px * side
            fy = hy + 2 + vy * 2 + py * side
            _fist(layer, fx, fy, skin)
        frames.append(_held(d, low, skin, draw))
    return frames


def _hurt(d: str, base: Image.Image) -> list[Image.Image]:
    vx, vy = VEC[d]
    return [_tint(_place(base), (255, 255, 255), 0.75), _tint(_place(base, -vx, -vy), (200, 40, 30), 0.3)]


def _death(d: str, base: Image.Image) -> list[Image.Image]:
    turn = -90 if d == "left" else 90  # tombe en arrière, du côté opposé au regard
    knees = _place(_crouch(base))
    def rot(img: Image.Image, deg: float) -> Image.Image:
        r = img.rotate(deg, resample=Image.NEAREST, center=(12, 18))
        box = r.getbbox()
        out = _canvas()
        if box:  # recalé : pieds/corps posés sur la ligne 21, centré horizontalement
            part = r.crop(box)
            out.alpha_composite(part, ((FRAME - part.width) // 2, FRAME - 3 - part.height))
        return out
    half = rot(knees, turn / 2)
    flat = rot(_place(base), turn)
    pool = _canvas()
    side = -1 if turn > 0 else 1  # flaque côté tête
    for x, y, c in ((0, 0, BLOOD), (1, 0, BLOOD), (2, 0, BLOOD_DARK), (0, 1, BLOOD_DARK), (1, 1, BLOOD),
                    (2, 1, BLOOD), (3, 1, BLOOD), (1, 2, BLOOD_DARK), (2, 2, BLOOD), (-1, 1, BLOOD)):
        _put(pool, 12 + side * (5 + x), 18 + y, c)
    bled = _canvas()
    bled.alpha_composite(pool)
    bled.alpha_composite(flat)
    return [knees, half, flat, bled]


def _zombie_arms(d: str, base: Image.Image, skin, reach: int, shift=(0, 0)) -> Image.Image:
    """Bras tendus devant soi (posture typique du zombie), longueur `reach`."""
    vx, vy = VEC[d]
    px, py = -vy, vx

    def draw(layer, hx, hy, ang):
        cx, cy = OFF_X + 8 + shift[0], OFF_Y + 11 + shift[1]
        for side in (-3, 3):
            sx, sy = cx + px * side, cy + py * side
            if d in ("left", "right") and side < 0:
                continue  # de profil, un seul bras visible
            for i in range(1, reach + 1):
                _put(layer, sx + vx * (i + 3), sy + vy * (i + 3), skin)

    body = _place(base, *shift)
    layer = _canvas()
    draw(layer, 0, 0, 0)
    return _compose(body, layer, behind=(d == "up"))


# --------------------------------------------------------------------------- planches
def survivor_frames(d: str, cells: list[Image.Image], skin) -> dict[str, list[Image.Image]]:
    """`cells` = [immobile, pas A, pas B] pour la direction `d` (cadres 16 px)."""
    still, step_a, step_b = cells
    return {
        "idle": [_place(still), _place(_breathe(still))],
        "walk": [_place(step_a), _place(still), _place(step_b), _place(still)],
        "run": [_place(step_a, 0, -1), _place(still), _place(step_b, 0, -1), _place(still)],
        "attack_fists": _attack_melee(d, still, skin, 0),
        "attack_knife": _attack_melee(d, still, skin, 3),
        "attack_bat": _attack_bat(d, still, skin),
        "shoot_pistol": _shoot(d, still, skin, False),
        "shoot_shotgun": _shoot(d, still, skin, True),
        "reload_pistol": _reload(d, still, skin, False),
        "reload_shotgun": _reload(d, still, skin, True),
        "search": _search(d, still, skin),
        "hurt": _hurt(d, still),
        "death": _death(d, still),
    }


def zombie_frames(d: str, cells: list[Image.Image], skin) -> dict[str, list[Image.Image]]:
    still, step_a, step_b = cells
    vx, vy = VEC[d]
    arms = lambda img, reach=3, shift=(0, 0): _zombie_arms(d, img, skin, reach, shift)  # noqa: E731
    return {
        "idle": [arms(still), arms(_sway(still, 1))],
        "walk": [arms(step_a), arms(_sway(still, 1)), arms(step_b), arms(_sway(still, -1))],
        "run": [arms(step_a, 4, (0, -1)), arms(still, 4), arms(step_b, 4, (0, -1)), arms(still, 4)],
        "attack": [arms(still, 2, (-vx, -vy)), arms(still, 5, (vx, vy)), arms(still, 4, (vx, vy))],
        "hurt": _hurt(d, still),
        "death": _death(d, still),
    }


def build_sheet(source: Image.Image, anims: tuple[Anim, ...], frames_for) -> tuple[Image.Image, dict]:
    """`source` = planche 3 × 4 de 16 px (lignes = DIRECTIONS). Renvoie la planche et son JSON."""
    per_dir = {}
    skin = _skin(source.crop((0, 0, BASE, BASE)))  # visage de face : la vraie couleur de peau
    for row, d in enumerate(DIRECTIONS):
        cells = [source.crop((c * BASE, row * BASE, (c + 1) * BASE, (row + 1) * BASE)) for c in range(3)]
        per_dir[d] = frames_for(d, cells, skin)
    rows = len(anims) * len(DIRECTIONS)
    sheet = Image.new("RGBA", (COLUMNS * FRAME, rows * FRAME), (0, 0, 0, 0))
    meta: dict[str, dict] = {}
    for a_index, anim in enumerate(anims):
        for d_index, d in enumerate(DIRECTIONS):
            row = a_index * len(DIRECTIONS) + d_index
            frames = per_dir[d][anim.name]
            assert len(frames) == anim.frames, (anim.name, d, len(frames))
            for col, img in enumerate(frames):
                sheet.alpha_composite(img, (col * FRAME, row * FRAME))
            meta[f"{anim.name}_{d}"] = {
                "frames": [row * COLUMNS + c for c in range(anim.frames)],
                "fps": anim.fps,
                "loop": anim.loop,
            }
    return sheet, meta
