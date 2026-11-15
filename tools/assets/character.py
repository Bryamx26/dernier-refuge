"""Système de personnages modulaires (paper doll) en pixel art, vue de profil vers la droite.

Création originale du projet : tout est dessiné par ce script, de façon déterministe, sans aucun
asset externe. Sorties dans `assets/characters/` :

    base/body_back.png, body_mid.png, body_front.png   corps neutre en 3 sous-calques
    base/body.png                                      corps complet (les 3 sous-calques empilés)
    equipment/<catégorie>/<nom>_<sous-calque>.png      un équipement = 1 à 3 sous-calques
    character.config.json                              canvas, ancres, ordre de rendu, catalogue

Règles d'alignement : tous les PNG font exactement CANVAS × CANVAS pixels, partagent l'origine
(0, 0) en haut à gauche et ne sont jamais recadrés ni redimensionnés. Un équipement est calculé à
partir des formes du corps (mêmes coordonnées), donc il tombe au pixel près, sans repositionnement.

Sous-calques : `back` (derrière le corps : bras et jambe éloignés), `mid` (tronc, tête, jambe
proche), `front` (bras proche, devant tout). C'est ce découpage qui permet à une manche, un sac ou
une arme de passer derrière ou devant le corps.

Usage : `python3 -I tools/assets/character.py` (génère) ou `--check` (vérifie l'alignement).
"""

from __future__ import annotations

import colorsys
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

CANVAS = 64
GROUND_Y = 56  # ligne de sol : contour sous les pieds (les pieds finissent en y = 55)
SUBLAYERS = ("back", "mid", "front")
CATEGORIES = ("head", "torso", "legs", "feet", "back", "hands", "weapons")

RGB = tuple[int, int, int]
Pt = tuple[int, int]
Shape = set[Pt]

# Points d'ancrage (pixels du canvas, origine en haut à gauche).
ANCHORS: dict[str, Pt] = {
    "head": (32, 27),
    "neck": (31, 34),
    "shoulder_near": (30, 37),
    "shoulder_far": (36, 37),
    "torso": (32, 40),
    "back": (26, 39),
    "pelvis": (32, 45),
    "hand_near": (27, 46),
    "hand_far": (40, 45),
    "foot_near": (30, 55),
    "foot_far": (36, 55),
    "ground": (32, 56),
}

# Ordre de rendu, du fond vers l'avant : (emplacement, sous-calque).
RENDER_ORDER: tuple[tuple[str, str], ...] = (
    ("back", "back"),
    ("body", "back"), ("legs", "back"), ("feet", "back"), ("torso", "back"), ("hands", "back"),
    ("weapons", "back"),
    ("body", "mid"), ("legs", "mid"), ("feet", "mid"), ("torso", "mid"), ("back", "mid"),
    ("head", "mid"), ("head", "front"),
    ("weapons", "mid"),
    ("body", "front"), ("torso", "front"), ("hands", "front"),
    ("weapons", "front"), ("back", "front"),
)


# --------------------------------------------------------------------------- formes
def ellipse(cx: float, cy: float, rx: float, ry: float) -> Shape:
    return {
        (x, y)
        for y in range(CANVAS)
        for x in range(CANVAS)
        if ((x + 0.5 - cx) / rx) ** 2 + ((y + 0.5 - cy) / ry) ** 2 <= 1.0
    }


def rect(x0: int, y0: int, x1: int, y1: int) -> Shape:
    return {(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)}


def capsule(ax: float, ay: float, bx: float, by: float, r: float) -> Shape:
    out = set()
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy or 1.0
    for y in range(CANVAS):
        for x in range(CANVAS):
            px, py = x + 0.5 - ax, y + 0.5 - ay
            t = max(0.0, min(1.0, (px * dx + py * dy) / length2))
            if math.hypot(px - t * dx, py - t * dy) <= r:
                out.add((x, y))
    return out


def grow(shape: Shape, sides: int = 1, up: int = 0, down: int = 0) -> Shape:
    """Épaissit une forme (un vêtement est un peu plus ample que le membre qu'il couvre)."""
    return {(x + dx, y + dy) for (x, y) in shape for dx in range(-sides, sides + 1) for dy in range(-up, down + 1)}


def rows(shape: Shape) -> tuple[int, int]:
    ys = [y for _, y in shape]
    return min(ys), max(ys)


def row(shape: Shape, y: int) -> list[int]:
    return sorted(x for (x, yy) in shape if yy == y)


# --------------------------------------------------------------------------- couleurs
def ramp(base: RGB) -> list[RGB]:
    """Rampe de 4 teintes : clair, base, ombre, ombre profonde (palette limitée par matière)."""
    h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in base))
    k = 1.0 - 0.45 * max(0.0, l - 0.45)  # les teintes claires se désaturent dans l'ombre

    def tone(dl: float, dh: float, ds: float) -> RGB:
        r, g, b = colorsys.hls_to_rgb((h + dh) % 1.0, max(0.0, min(1.0, l * dl)), max(0.0, min(1.0, s * ds)))
        return (round(r * 255), round(g * 255), round(b * 255))

    return [tone(1.1, 0.012, 0.9), base, tone(0.78, -0.015, 0.92 * k), tone(0.58, -0.03, 0.85 * k)]


def darker(c: RGB, k: float) -> RGB:
    return (round(c[0] * k), round(c[1] * k), round(c[2] * k))


SKIN: RGB = (226, 184, 146)
MATERIALS: dict[str, RGB] = {
    "kaki": (104, 116, 72),
    "casque": (86, 100, 76),
    "cuir": (96, 64, 44),
    "laiton": (216, 176, 80),
}


# --------------------------------------------------------------------------- corps
@dataclass(frozen=True)
class Part:
    name: str
    sublayer: str
    shape: frozenset


def body_parts() -> list[Part]:
    """Membres du corps neutre, profil droit, bras légèrement écartés. Ordre = superposition."""
    def p(name: str, sub: str, shape: Shape) -> Part:
        return Part(name, sub, frozenset(shape))

    torso = rect(27, 35, 37, 44) - {(27, 35), (37, 35)}
    pelvis = rect(27, 43, 37, 46) - {(27, 46), (37, 46)}
    return [
        p("arm_far", "back", capsule(36.2, 37.2, 39.8, 43.2, 1.8)),
        p("hand_far", "back", ellipse(40.5, 45.2, 1.8, 1.9)),
        p("leg_far", "back", capsule(35.2, 46.0, 36.2, 53.0, 2.4)),
        p("foot_far", "back", rect(34, 54, 40, 55)),
        p("leg_near", "mid", capsule(30.0, 46.0, 29.6, 53.0, 2.6)),
        p("foot_near", "mid", rect(27, 54, 33, 55)),
        p("pelvis", "mid", pelvis),
        p("torso", "mid", torso),
        p("neck", "mid", rect(30, 33, 33, 34)),
        p("head", "mid", ellipse(32.5, 27.5, 6.6, 6.2) | {(39, 29)}),
        p("arm_near", "front", capsule(30.0, 37.4, 28.0, 43.6, 2.0)),
        p("hand_near", "front", ellipse(27.4, 45.7, 1.9, 2.0)),
    ]


def body_shape(parts: list[Part], sublayer: str | None = None) -> Shape:
    out: Shape = set()
    for part in parts:
        if sublayer is None or part.sublayer == sublayer:
            out |= part.shape
    return out


# --------------------------------------------------------------------------- rendu
@dataclass
class Piece:
    """Morceau d'un sous-calque : forme + couleur. L'ordre dans la liste = superposition."""

    shape: Shape
    color: RGB


def render(pieces: list[Piece], mask: Shape, details: dict[Pt, RGB] | None = None, dim: float = 1.0) -> Image.Image:
    """Ombre chaque morceau (lumière en haut à gauche), contour sombre hors de `mask`, détails.

    `mask` = silhouette du corps dans ce sous-calque : un vêtement ne trace pas de contour sur
    le corps qu'il recouvre, seulement autour de sa propre silhouette.
    `dim` assombrit tout le sous-calque (membres éloignés, à l'arrière-plan).
    """
    owner: dict[Pt, int] = {}
    for i, piece in enumerate(pieces):
        for pt in piece.shape:
            assert 0 <= pt[0] < CANVAS and 0 <= pt[1] < CANVAS, f"hors canvas : {pt}"
            owner[pt] = i
    ramps = [[darker(c, dim) for c in ramp(p.color)] for p in pieces]
    img = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    for (x, y), i in owner.items():
        xl = x
        while owner.get((xl - 1, y)) == i:
            xl -= 1
        xr = x
        while owner.get((xr + 1, y)) == i:
            xr += 1
        w, pos = xr - xl + 1, x - xl
        tone = 1
        if (w >= 3 and pos == 0) or (w >= 7 and pos == 1):
            tone = 0
        if owner.get((x, y - 1)) != i and tone == 1 and pos < w * 0.6:
            tone = 0
        if (w >= 2 and pos == w - 1) or (w >= 6 and pos >= w - 2):
            tone = 2
        if owner.get((x, y + 1)) != i:
            tone = max(tone, 2)
        for n in ((x + 1, y), (x, y + 1)):  # ombre portée sous un morceau plus proche
            j = owner.get(n)
            if j is not None and j > i:
                tone = 3
        img.putpixel((x, y), (*ramps[i][tone], 255))
    for (x, y), i in list(owner.items()):
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if n not in owner and n not in mask and 0 <= n[0] < CANVAS and 0 <= n[1] < CANVAS:
                img.putpixel(n, (*darker(ramps[i][3], 0.5), 255))
    for pt, c in (details or {}).items():
        img.putpixel(pt, (*darker(c, dim), 255))
    return img


Layers = dict[str, Image.Image]  # sous-calque → image CANVAS × CANVAS


def draw_body() -> Layers:
    parts = body_parts()
    sk = ramp(SKIN)
    out: Layers = {}
    for sub in SUBLAYERS:
        pieces = [Piece(set(p.shape), SKIN) for p in parts if p.sublayer == sub]
        det: dict[Pt, RGB] = {}
        if sub == "mid":  # visage de profil : œil, sourcil, oreille, bouche ; anatomie neutre
            eye = (38, 32, 40)
            det.update({(36, 27): eye, (36, 28): eye, (35, 27): (246, 242, 234), (35, 25): sk[3], (36, 25): sk[3], (37, 25): sk[3]})
            det.update({(31, 27): sk[2], (31, 28): sk[3], (30, 28): sk[2], (31, 29): sk[2]})
            det.update({(37, 31): sk[3], (36, 31): sk[2]})
            det.update({(35, 39): sk[2], (36, 39): sk[2]})  # pli de poitrine, discret
        out[sub] = render(pieces, set(), det, dim=0.86 if sub == "back" else 1.0)
    return out


# --------------------------------------------------------------------------- équipements de test
def draw_jacket() -> Layers:
    """Veste kaki (catégorie torso) : tronc + les deux manches, chacune sur son sous-calque."""
    parts = {p.name: set(p.shape) for p in body_parts()}
    color = MATERIALS["kaki"]
    r = ramp(color)
    trunk = grow(parts["torso"]) | grow({q for q in parts["pelvis"] if q[1] <= 44}) | rect(30, 34, 34, 34)
    y0, y1 = rows(trunk)
    for y in range(y0, y1 + 1):  # tombé droit : pas de creux
        xs = row(trunk, y)
        trunk |= {(x, y) for x in range(xs[0], xs[-1] + 1)}
    sleeve_near = grow(parts["arm_near"])
    sleeve_far = grow(parts["arm_far"])
    mid_det: dict[Pt, RGB] = {(x, y1): r[3] for x in row(trunk, y1)}  # ourlet
    front_edge = max(row(trunk, 40))
    for y in range(36, y1):  # patte de boutonnage sur le devant
        mid_det[(front_edge - 1, y)] = r[2]
    mid_det.update({(front_edge - 1, 37): MATERIALS["laiton"], (front_edge - 1, 41): MATERIALS["laiton"]})
    mid_det.update({(33, 34): r[0], (34, 34): r[0], (35, 35): r[0], (32, 34): r[2]})  # col
    mid_det.update({(33, 42): r[2], (34, 42): r[2], (35, 42): r[2], (36, 42): r[2]})  # poche
    def cuff(shape: Shape) -> dict[Pt, RGB]:
        y = rows(shape)[1]
        return {(x, y): r[3] for x in row(shape, y)}
    front_det = cuff(sleeve_near)
    front_det.update({(29, 38): r[2], (30, 38): r[2], (31, 38): r[2]})  # couture d'épaule
    body = body_parts()
    return {
        "back": render([Piece(sleeve_far, color)], body_shape(body, "back"), cuff(sleeve_far), dim=0.86),
        "mid": render([Piece(trunk, color)], body_shape(body, "mid"), mid_det),
        "front": render([Piece(sleeve_near, color)], body_shape(body, "front"), front_det),
    }


def draw_helmet() -> Layers:
    """Casque (catégorie head) : une coque devant la tête, jugulaire comprise."""
    color = MATERIALS["casque"]
    r = ramp(color)
    shell = {q for q in ellipse(32.5, 27.2, 7.7, 7.4) if q[1] <= 25} | {(40, 25), (41, 25)}
    rim = rows(shell)[1]
    det: dict[Pt, RGB] = {(x, rim): r[3] for x in row(shell, rim)}
    det.update({(28, 22): r[0], (29, 21): r[0], (30, 21): r[0], (28, 23): r[0]})  # reflet
    strap = darker(MATERIALS["cuir"], 0.8)
    det.update({(33, 26): strap, (33, 27): strap, (34, 28): strap, (34, 29): strap, (35, 30): strap, (35, 31): strap, (36, 32): strap})
    return {"front": render([Piece(shell, color)], body_shape(body_parts(), "mid"), det)}


# Catalogue : nom → définition. C'est ici qu'on ajoutera les centaines d'équipements.
ITEMS = {
    "veste_kaki": {
        "category": "torso",
        "draw": draw_jacket,
        "covers": ["torso", "arm_near", "arm_far"],
        "requires": [], "hides": [], "conflicts": [],
    },
    "casque_militaire": {
        "category": "head",
        "draw": draw_helmet,
        "covers": [],
        "requires": [], "hides": ["head:hair_top"], "conflicts": ["head:hood"],
    },
}


# --------------------------------------------------------------------------- assemblage
def compose(equipped: list[str]) -> Image.Image:
    """Empile corps et équipements selon RENDER_ORDER, sans aucun décalage (comme le fera le jeu)."""
    stacks: dict[tuple[str, str], list[Image.Image]] = {}
    for sub, img in draw_body().items():
        stacks.setdefault(("body", sub), []).append(img)
    for name in equipped:
        item = ITEMS[name]
        for sub, img in item["draw"]().items():
            stacks.setdefault((item["category"], sub), []).append(img)
    out = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    for key in RENDER_ORDER:
        for img in stacks.get(key, []):
            out.alpha_composite(img)
    return out


def opaque(img: Image.Image) -> Shape:
    px = img.load()
    return {(x, y) for y in range(img.height) for x in range(img.width) if px[x, y][3]}


def check() -> list[str]:
    """Vérifie l'alignement. Renvoie la liste des anomalies (vide = tout est aligné)."""
    errors: list[str] = []
    parts = {p.name: p for p in body_parts()}
    body = draw_body()
    for sub, img in body.items():
        if img.size != (CANVAS, CANVAS):
            errors.append(f"corps/{sub} : taille {img.size}")
    if max(y for _, y in opaque(compose([]))) != GROUND_Y:  # contour compris
        errors.append("le corps ne repose pas sur la ligne de sol")
    for name, pt in ANCHORS.items():
        if not (0 <= pt[0] < CANVAS and 0 <= pt[1] <= CANVAS):
            errors.append(f"ancre {name} hors canvas")
    for name, item in ITEMS.items():
        layers = item["draw"]()
        for sub, img in layers.items():
            if img.size != (CANVAS, CANVAS):
                errors.append(f"{name}/{sub} : taille {img.size} au lieu de {CANVAS}×{CANVAS}")
            if (item["category"], sub) not in RENDER_ORDER:
                errors.append(f"{name}/{sub} : absent de l'ordre de rendu")
        # Chaque membre annoncé comme couvert doit l'être entièrement, sur le bon sous-calque.
        worn = opaque(compose([name]))
        skin_tones = {(*c, 255) for c in ramp(SKIN)} | {(*darker(c, 0.86), 255) for c in ramp(SKIN)}
        result = compose([name]).load()
        for member in item["covers"]:
            part = parts[member]
            layer = layers.get(part.sublayer)
            missing = set(part.shape) - (opaque(layer) if layer else set())
            if missing:
                errors.append(f"{name} : {len(missing)} pixel(s) de {member} non couverts, ex. {sorted(missing)[:3]}")
            visible = [q for q in part.shape if result[q[0], q[1]] in skin_tones]
            if visible and member != "arm_far":
                errors.append(f"{name} : peau visible sur {member} en {visible[:3]}")
        if not worn >= opaque(compose([])):
            errors.append(f"{name} : la silhouette équipée perd des pixels du corps")
    return errors


def config() -> dict:
    return {
        "_comment": "AUTO-GÉNÉRÉ par tools/assets/character.py. Ne pas modifier à la main.",
        "canvas": {"width": CANVAS, "height": CANVAS, "origin": "top-left", "ground_y": GROUND_Y, "facing": "right",
                   "mirror_for_left": True, "pivot": list(ANCHORS["ground"])},
        "anchors": {k: list(v) for k, v in ANCHORS.items()},
        "sublayers": list(SUBLAYERS),
        "categories": list(CATEGORIES),
        "render_order": [f"{slot}:{sub}" for slot, sub in RENDER_ORDER],
        "base": {sub: f"base/body_{sub}.png" for sub in SUBLAYERS},
        "items": {
            name: {
                "category": item["category"],
                "layers": {sub: f"equipment/{item['category']}/{name}_{sub}.png" for sub in item["draw"]()},
                "covers": item["covers"],
                "requires": item["requires"], "hides": item["hides"], "conflicts": item["conflicts"],
            }
            for name, item in ITEMS.items()
        },
    }


def main() -> None:
    errors = check()
    if "--check" in sys.argv:
        print("\n".join(errors) if errors else f"Alignement vérifié : {len(ITEMS)} équipement(s), aucune anomalie.")
        sys.exit(1 if errors else 0)
    assert not errors, errors
    root = Path(__file__).resolve().parents[2] / "assets" / "characters"
    (root / "base").mkdir(parents=True, exist_ok=True)
    for sub, img in draw_body().items():
        img.save(root / "base" / f"body_{sub}.png")
    compose([]).save(root / "base" / "body.png")
    for category in CATEGORIES:
        (root / "equipment" / category).mkdir(parents=True, exist_ok=True)
        (root / "equipment" / category / ".gitkeep").touch()
    for name, item in ITEMS.items():
        for sub, img in item["draw"]().items():
            img.save(root / "equipment" / item["category"] / f"{name}_{sub}.png")
    (root / "character.config.json").write_text(json.dumps(config(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
