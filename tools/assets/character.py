"""Personnage modulaire « poupée de papier », style 16 bits : corps de base + pièces équipables.

Création originale du projet (aucun asset externe) : tout est dessiné par ce script, de façon
déterministe. Un personnage est un empilement de calques de même taille (32 × 48 px) :

    corps (sexe, couleur de peau) < pantalon < veste < cheveux < couvre-chef < sac à dos

Le corps est un petit squelette : chaque membre est une forme (capsule, ellipse, rectangle) posée
entre des articulations. Les vêtements sont calculés à partir de ces mêmes formes (le pantalon
recouvre les jambes, la veste le torse et les bras, un peu plus amples). Animer le personnage
reviendra à déplacer les articulations : toutes les pièces suivront.

Rendu : chaque matière a une rampe de 4 teintes (clair, base, ombre, ombre profonde) avec un
léger décalage de teinte, lumière en haut à gauche, contour sombre, puis des détails posés à la
main (visage, poches, fermeture, boucles, reflets).

Planche d'un calque : 4 cadres côte à côte, dans l'ordre DIRECTIONS (bas, gauche, droite, haut).
"""

from __future__ import annotations

import colorsys
import math
from dataclasses import dataclass

from PIL import Image, ImageOps

FRAME_W, FRAME_H = 32, 48
DIRECTIONS = ("down", "left", "right", "up")

RGB = tuple[int, int, int]
Pt = tuple[int, int]
Shape = set[Pt]


# --------------------------------------------------------------------------- formes
def ellipse(cx: float, cy: float, rx: float, ry: float) -> Shape:
    return {
        (x, y)
        for y in range(FRAME_H)
        for x in range(FRAME_W)
        if ((x + 0.5 - cx) / rx) ** 2 + ((y + 0.5 - cy) / ry) ** 2 <= 1.0
    }


def rect(x0: int, y0: int, x1: int, y1: int) -> Shape:
    return {(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)}


def capsule(ax: float, ay: float, bx: float, by: float, r: float) -> Shape:
    out = set()
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy or 1.0
    for y in range(FRAME_H):
        for x in range(FRAME_W):
            px, py = x + 0.5 - ax, y + 0.5 - ay
            t = max(0.0, min(1.0, (px * dx + py * dy) / length2))
            if math.hypot(px - t * dx, py - t * dy) <= r:
                out.add((x, y))
    return out


def widen(shape: Shape, n: int = 1) -> Shape:
    """Élargit horizontalement de n pixels de chaque côté (vêtement ample)."""
    return {(x + d, y) for (x, y) in shape for d in range(-n, n + 1)}


def flip(shape: Shape) -> Shape:
    return {(FRAME_W - 1 - x, y) for (x, y) in shape}


# --------------------------------------------------------------------------- couleurs
def ramp(base: RGB) -> list[RGB]:
    """Rampe 16 bits : clair (tire vers le chaud), base, ombre et ombre profonde (vers le froid)."""
    h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in base))

    def tone(dl: float, dh: float, ds: float) -> RGB:
        r, g, b = colorsys.hls_to_rgb((h + dh) % 1.0, max(0.0, min(1.0, l * dl)), max(0.0, min(1.0, s * ds)))
        return (round(r * 255), round(g * 255), round(b * 255))

    # Les teintes claires (peau, tissu clair) se désaturent dans l'ombre pour ne pas virer à l'orange.
    k = 1.0 - 0.45 * max(0.0, l - 0.45)
    return [tone(1.1, 0.012, 0.9), base, tone(0.78, -0.015, 0.92 * k), tone(0.58, -0.03, 0.85 * k)]


def darker(c: RGB, k: float) -> RGB:
    return (round(c[0] * k), round(c[1] * k), round(c[2] * k))


SKINS: dict[str, RGB] = {
    "claire": (240, 198, 162),
    "mate": (212, 160, 116),
    "brune": (158, 106, 72),
    "noire": (104, 68, 50),
}
HAIR_COLORS: dict[str, RGB] = {
    "noir": (52, 46, 52),
    "brun": (108, 68, 40),
    "blond": (218, 178, 94),
    "roux": (184, 84, 40),
}
MATERIALS: dict[str, RGB] = {
    "sousvet": (112, 122, 138),
    "jean": (64, 86, 132),
    "cuir": (96, 64, 44),
    "kaki": (104, 116, 72),
    "casque": (86, 100, 76),
    "casquette": (164, 58, 50),
    "sac": (136, 104, 62),
    "combi": (212, 208, 190),
    "caoutchouc": (62, 64, 72),
    "verre": (84, 188, 184),
    "orange": (230, 128, 40),
    "laiton": (216, 176, 80),
}


# --------------------------------------------------------------------------- squelette
@dataclass(frozen=True)
class Part:
    name: str
    shape: frozenset


def _p(name: str, shape: Shape) -> Part:
    return Part(name, frozenset(shape))


def body_parts(sex: str, view: str) -> list[Part]:
    """Membres du corps, du plus éloigné au plus proche. `view` : front | back | side (regard à droite)."""
    f = sex == "f"
    if view in ("front", "back"):
        leg_l = capsule(13.5, 31, 13.5, 43, 2.0 if not f else 1.9)
        foot_l = rect(10, 44, 14, 45)
        arm_l = capsule(10.2, 20.4, 9.8, 28.6, 1.3) if f else capsule(9.5, 20.2, 9.0, 28.8, 1.6)
        hand_l = ellipse(9.8 if f else 9.0, 30.6, 1.5, 1.9)
        if f:
            torso = rect(11, 18, 20, 23) | rect(12, 24, 19, 27)
            pelvis = rect(11, 28, 20, 31)
        else:
            torso = rect(10, 18, 21, 19) | rect(11, 20, 20, 27)
            pelvis = rect(11, 28, 20, 31)
        return [
            _p("leg_l", leg_l), _p("leg_r", flip(leg_l)), _p("foot_l", foot_l), _p("foot_r", flip(foot_l)),
            _p("pelvis", pelvis), _p("torso", torso), _p("neck", rect(14, 16, 17, 17)),
            _p("arm_l", arm_l), _p("arm_r", flip(arm_l)), _p("hand_l", hand_l), _p("hand_r", flip(hand_l)),
            _p("head", ellipse(16, 10.5, 5.0, 5.8)),
        ]
    torso = rect(13, 18, 19, 27) | (rect(14, 19, 20, 23) if not f else rect(14, 20, 20, 22))
    if f:
        torso -= rect(19, 24, 19, 27)
    return [
        _p("leg_far", capsule(15.0, 31, 14.8, 43, 1.9)), _p("foot_far", rect(13, 44, 18, 45)),
        _p("leg_near", capsule(16.6, 31, 16.4, 43, 2.1)), _p("foot_near", rect(14, 44, 20, 45)),
        _p("pelvis", rect(13, 28, 19, 31)), _p("torso", torso), _p("neck", rect(15, 16, 17, 17)),
        _p("head", ellipse(16.3, 10.5, 5.0, 5.8) | {(21, 12)}),
        _p("arm", capsule(16.0, 20.2, 16.4, 28.8, 1.3 if f else 1.6)), _p("hand", ellipse(16.5, 30.6, 1.5, 1.9)),
    ]


def silhouette(parts: list[Part]) -> Shape:
    out: Shape = set()
    for p in parts:
        out |= p.shape
    return out


# --------------------------------------------------------------------------- rendu
@dataclass
class Piece:
    """Un morceau de calque : forme + matière. L'ordre dans la liste = ordre de superposition."""

    shape: Shape
    color: RGB


def render(pieces: list[Piece], body: Shape, details: dict[Pt, RGB] | None = None,
           tones: dict[Pt, int] | None = None) -> Image.Image:
    """Ombre chaque morceau, trace le contour hors silhouette du corps, pose les détails."""
    owner: dict[Pt, int] = {}
    for i, piece in enumerate(pieces):
        for pt in piece.shape:
            if 0 <= pt[0] < FRAME_W and 0 <= pt[1] < FRAME_H:
                owner[pt] = i
    ramps = [ramp(p.color) for p in pieces]
    img = Image.new("RGBA", (FRAME_W, FRAME_H), (0, 0, 0, 0))
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
        # Ombre portée : ce morceau passe sous un morceau plus proche, à droite ou en dessous.
        for n in ((x + 1, y), (x, y + 1)):
            j = owner.get(n)
            if j is not None and j > i:
                tone = 3
        if tones and (x, y) in tones:
            tone = tones[(x, y)]
        img.putpixel((x, y), (*ramps[i][tone], 255))
    for (x, y), i in list(owner.items()):
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if n not in owner and n not in body and 0 <= n[0] < FRAME_W and 0 <= n[1] < FRAME_H:
                img.putpixel(n, (*darker(ramps[i][3], 0.55), 255))
    for pt, c in (details or {}).items():
        if 0 <= pt[0] < FRAME_W and 0 <= pt[1] < FRAME_H:
            img.putpixel(pt, (*c, 255))
    return img


def _named(parts: list[Part], *prefixes: str) -> list[Part]:
    return [p for p in parts if p.name.startswith(prefixes)]


def _rows(shape: Shape) -> tuple[int, int]:
    ys = [y for _, y in shape]
    return min(ys), max(ys)


def _row(shape: Shape, y: int) -> list[int]:
    return sorted(x for (x, yy) in shape if yy == y)


# --------------------------------------------------------------------------- corps
def draw_body(sex: str, view: str, skin: RGB) -> Image.Image:
    parts = body_parts(sex, view)
    sk = ramp(skin)
    under = ramp(MATERIALS["sousvet"])
    pieces = [Piece(set(p.shape), skin) for p in parts]
    det: dict[Pt, RGB] = {}
    pelvis = next(p for p in parts if p.name == "pelvis").shape
    torso = next(p for p in parts if p.name == "torso").shape
    # Sous-vêtements : slip (ceinture claire) ; brassière pour le corps féminin.
    y0, y1 = _rows(pelvis)
    for (x, y) in pelvis:
        edge = x == _row(pelvis, y)[-1]
        det[(x, y)] = under[0] if y == y0 else under[2] if (edge or y == y1) else under[1]
    if sex == "f":
        for (x, y) in torso:
            if 20 <= y <= 22:
                xs = _row(torso, y)
                det[(x, y)] = under[0] if y == 20 and x < xs[-1] - 1 else under[2] if (x >= xs[-1] - 1 or y == 22) else under[1]
    eye, white = (34, 28, 36), (244, 240, 232)
    brow = darker(sk[3], 0.8)
    lips = (188, 96, 92) if sex == "f" else sk[3]
    if view == "front":
        det.update({(13, 11): white, (14, 11): eye, (17, 11): eye, (18, 11): white})
        det.update({(13, 9): brow, (14, 9): brow, (17, 9): brow, (18, 9): brow})
        det.update({(16, 12): sk[2], (16, 13): sk[2], (15, 14): lips, (16, 14): lips})
        det.update({(10, 11): sk[1], (10, 12): sk[2], (21, 11): sk[2], (21, 12): sk[3]})  # oreilles
        if sex == "m":
            det.update({(13, 23): sk[2], (14, 23): sk[2], (17, 23): sk[2], (18, 23): sk[2], (16, 26): sk[2]})  # pectoraux, nombril
        else:
            det.update({(13, 10): eye, (18, 10): eye})  # cils
        det.update({(15, 17): sk[2], (16, 17): sk[2], (17, 17): sk[3]})
    elif view == "side":
        det.update({(18, 11): white, (19, 11): eye, (18, 9): brow, (19, 9): brow, (19, 14): lips, (20, 14): lips})
        det.update({(15, 11): sk[2], (15, 12): sk[3], (14, 11): sk[2]})  # oreille
        if sex == "f":
            det[(19, 10)] = eye
    else:
        det.update({(10, 11): sk[1], (10, 12): sk[2], (21, 11): sk[2], (21, 12): sk[3]})
        det.update({(15, 22): sk[2], (16, 22): sk[2], (15, 25): sk[2], (16, 25): sk[2]})  # colonne
    if view != "side":
        for x in (10, 21):  # contour des oreilles
            det.setdefault((x, 10), darker(sk[3], 0.55))
            det.setdefault((x, 13), darker(sk[3], 0.55))
    return render(pieces, set(), det)


# --------------------------------------------------------------------------- vêtements
def draw_pants(sex: str, view: str, color: RGB, boots: RGB, baggy: bool = False, tall_boots: int = 2,
               band: RGB | None = None) -> Image.Image:
    parts = body_parts(sex, view)
    body = silhouette(parts)
    cut = 44 - tall_boots
    pieces: list[Piece] = []
    for p in _named(parts, "leg"):
        shape = widen(set(p.shape)) if baggy else set(p.shape)
        pieces.append(Piece({q for q in shape if q[1] < cut}, color))
    pelvis = set(next(p for p in parts if p.name == "pelvis").shape)
    pieces.append(Piece(widen(pelvis) if baggy else pelvis, color))
    boot_shapes = []
    for leg, foot in zip(_named(parts, "leg"), _named(parts, "foot")):
        shape = widen({q for q in leg.shape if q[1] >= cut}) | set(foot.shape) | {(x, y - 1) for (x, y) in foot.shape if y == 44}
        boot_shapes.append(shape)
        pieces.append(Piece(shape, boots))
    r, b = ramp(color), ramp(boots)
    det: dict[Pt, RGB] = {}
    for shape in boot_shapes:
        y1 = _rows(shape)[1]
        for (x, y) in shape:
            if y == y1:
                det[(x, y)] = darker(b[3], 0.7)  # semelle
            if band and y == cut:
                det[(x, y)] = band
    y0 = _rows(pelvis)[0]
    if not baggy:  # ceinture, boucle, poches, braguette, pli du genou
        belt = ramp(MATERIALS["cuir"])
        for x in _row(pieces[-len(boot_shapes) - 1].shape, y0):
            det[(x, y0)] = belt[2]
        if view == "front":
            det.update({(15, y0): MATERIALS["laiton"], (16, y0): MATERIALS["laiton"]})
            det.update({(12, y0 + 2): r[2], (13, y0 + 1): r[2], (19, y0 + 2): r[2], (18, y0 + 1): r[2], (16, y0 + 1): r[2], (16, y0 + 2): r[2]})
            det.update({(12, 37): r[2], (13, 37): r[2], (18, 37): r[2], (19, 37): r[2]})
        elif view == "back":
            det.update({(12, y0 + 2): r[2], (13, y0 + 2): r[2], (14, y0 + 2): r[2], (17, y0 + 2): r[2], (18, y0 + 2): r[2], (19, y0 + 2): r[2]})
            det.update({(12, y0 + 3): r[2], (14, y0 + 3): r[2], (17, y0 + 3): r[2], (19, y0 + 3): r[2]})
        else:
            det.update({(15, y0 + 1): r[2], (16, y0 + 2): r[2], (16, y0 + 3): r[2], (17, 37): r[2], (18, 37): r[2]})
    else:  # plis de la combinaison
        if view == "side":
            det.update({(16, 36): r[2], (17, 37): r[2], (18, 37): r[2], (15, 33): r[2]})
        else:
            det.update({(12, 36): r[2], (13, 37): r[2], (19, 36): r[2], (18, 37): r[2], (15, 32): r[3], (16, 32): r[3]})
    return render(pieces, body, det)


def draw_jacket(sex: str, view: str, color: RGB, style: str) -> Image.Image:
    """style = « veste » (col, fermeture, poches) ou « combi » (coutures, brassards, gants)."""
    parts = body_parts(sex, view)
    body = silhouette(parts)
    torso = set(next(p for p in parts if p.name == "torso").shape)
    pelvis = next(p for p in parts if p.name == "pelvis").shape
    py0 = _rows(pelvis)[0]
    trunk = widen(torso) | widen({q for q in pelvis if q[1] <= py0 + 1})
    ty0, ty1 = _rows(trunk)
    # Comble la taille : une veste tombe droit depuis les épaules.
    for y in range(ty0, ty1 + 1):
        xs = _row(trunk, y)
        trunk |= {(x, y) for x in range(xs[0], xs[-1] + 1)}
    neck = next(p for p in parts if p.name == "neck").shape
    collar = widen({q for q in neck if q[1] == 17})
    sleeves = [Piece(widen(set(p.shape)), color) for p in _named(parts, "arm")]
    gloves = [Piece(widen(set(p.shape)) | set(p.shape), MATERIALS["caoutchouc"]) for p in _named(parts, "hand")] if style == "combi" else []
    if view == "side":
        pieces = [Piece(trunk | collar, color)] + sleeves + gloves
    else:
        pieces = sleeves + gloves + [Piece(trunk | collar, color)]
    r = ramp(color)
    det: dict[Pt, RGB] = {}
    for x in _row(trunk, ty1):
        det[(x, ty1)] = r[3]  # ourlet
    for s in sleeves:  # poignets
        y1 = _rows(s.shape)[1]
        for x in _row(s.shape, y1):
            det[(x, y1)] = r[3]
    if style == "veste":
        if view == "front":
            for y in range(19, ty1):
                det[(16, y)] = r[3]
                det[(15, y)] = r[0]
            det.update({(14, 17): r[0], (13, 18): r[0], (14, 18): r[0], (17, 17): r[1], (17, 18): r[1], (18, 18): r[2]})
            det.update({(15, 19): MATERIALS["laiton"]})
            for x in (12, 13, 14, 18, 19, 20):  # poches à rabat
                det[(x, 25)] = r[2]
                det[(x, 23)] = r[2] if x in (12, 20) else r[1]
            det.update({(12, 21): r[2], (20, 21): r[2]})  # coutures d'épaule
        elif view == "back":
            for x in range(12, 20):
                det[(x, 21)] = r[2]
            det.update({(16, y): r[2] for y in range(22, ty1)})
            det.update({(x, 17): r[0] for x in range(14, 18)})
        else:
            det.update({(18, 17): r[0], (19, 18): r[0]})
            for y in range(19, ty1):
                det[(20 if (20, y) in trunk else 19, y)] = r[2]
            det.update({(18, 25): r[2], (19, 25): r[2]})
    else:
        orange = ramp(MATERIALS["orange"])
        for s in sleeves:
            for (x, y) in s.shape:
                if y in (22, 23):
                    xs = _row(s.shape, y)
                    det[(x, y)] = orange[2] if x == xs[-1] else orange[1] if y == 23 else orange[0]
        if view == "front":
            for y in range(19, ty1):
                det[(16, y)] = r[2]
            det.update({(13, 21): r[2], (14, 21): r[2], (13, 22): r[2], (14, 22): r[2], (13, 23): r[2], (14, 23): r[2]})  # poche poitrine
            det.update({(13, 21): r[0], (14, 21): r[0]})
            det.update({(x, 27): r[2] for x in range(11, 21)})  # ceinture élastique
        elif view == "back":
            det.update({(16, y): r[2] for y in range(19, ty1)})
            det.update({(x, 27): r[2] for x in range(11, 21)})
            det.update({(x, 20): orange[1] for x in range(13, 19)})
        else:
            det.update({(x, 27): r[2] for x in range(13, 20)})
    return render(pieces, body, det)


# --------------------------------------------------------------------------- tête : cheveux, coiffes
def _head_cx(view: str) -> float:
    return 16.3 if view == "side" else 16.0


def draw_hair(sex: str, view: str, style: str, color: RGB) -> Image.Image:
    body = silhouette(body_parts(sex, view))
    cx = _head_cx(view)
    dome = ellipse(cx, 10.3, 5.9, 6.4)
    r = ramp(color)
    pieces: list[Piece] = []
    det: dict[Pt, RGB] = {}
    if view == "front":
        cap = {q for q in dome if q[1] <= 8 or (q[1] <= 11 and (q[0] <= 10 or q[0] >= 21))} | {(11, 9), (12, 9), (13, 9), (19, 9), (20, 9), (11, 10), (20, 10)}
        if style == "long":
            pieces.append(Piece(rect(9, 9, 11, 25) | rect(20, 9, 22, 25) | rect(10, 26, 11, 26) | rect(20, 26, 21, 26), color))
            cap |= {(14, 9)}
        pieces.append(Piece(cap, color))
        det.update({(x, 6): r[0] for x in (12, 13, 14, 15)})
        det.update({(16, 5): r[2], (16, 6): r[2], (17, 7): r[2]} if style != "court" else {(13, 7): r[0]})
    elif view == "side":
        cap = {q for q in dome if q[1] <= 8 or (q[0] <= 14 and q[1] <= 13)} | {(18, 9), (19, 9)}
        if style == "long":
            pieces.append(Piece(rect(10, 9, 14, 25) | rect(11, 26, 13, 26), color))
        if style == "queue":
            pieces.append(Piece(capsule(10.5, 9.5, 8.5, 18.5, 1.5), color))
            det.update({(10, 10): MATERIALS["casquette"], (11, 10): MATERIALS["casquette"]})
        pieces.append(Piece(cap, color))
        det.update({(x, 6): r[0] for x in (13, 14, 15, 16)})
        det.update({(15, 10): r[2], (15, 12): r[2]})
    else:
        cap = {q for q in dome if q[1] <= 14}
        if style == "long":
            cap |= rect(10, 9, 21, 25) | rect(11, 26, 20, 26)
            det.update({(x, y): r[2] for x in (13, 17) for y in range(12, 26)})  # mèches
            det.update({(x, y): r[0] for x in (11, 15) for y in range(10, 22)})
        pieces.append(Piece(cap, color))
        if style == "queue":
            pieces.append(Piece(capsule(16, 11, 16, 21, 1.6), color))
            det.update({(15, 11): MATERIALS["casquette"], (16, 11): MATERIALS["casquette"]})
        det.update({(x, 6): r[0] for x in (12, 13, 14, 15)})
        det.update({(13, 10): r[2], (17, 11): r[2], (15, 13): r[2]} if style != "long" else {})
    return render(pieces, body, det)


def draw_helmet(sex: str, view: str) -> Image.Image:
    body = silhouette(body_parts(sex, view))
    c = MATERIALS["casque"]
    r = ramp(c)
    cx = _head_cx(view)
    shell = {q for q in ellipse(cx, 10.2, 6.7, 6.9) if q[1] <= (11 if view == "back" else 9)}
    det: dict[Pt, RGB] = {}
    rim = _rows(shell)[1]
    for x in _row(shell, rim):
        det[(x, rim)] = r[3]
    det.update({(12, 5): r[0], (13, 4): r[0], (14, 4): r[0], (12, 6): r[0]})  # reflet
    strap = darker(MATERIALS["cuir"], 0.8)
    if view == "front":
        det.update({(x, y): strap for x in (11, 20) for y in range(10, 15)})
        det.update({(12, 15): strap, (19, 15): strap, (15, 7): r[2], (16, 7): r[2], (15, 6): r[2], (16, 6): r[2]})
    elif view == "side":
        shell |= {(22, 9), (23, 9)}
        det.update({(22, 9): r[3], (23, 9): r[3], (16, 10): strap, (17, 11): strap, (17, 12): strap, (18, 13): strap, (18, 14): strap, (19, 15): strap})
    else:
        det.update({(x, 8): r[2] for x in range(11, 21)})
    return render([Piece(shell, c)], body, det)


def draw_cap(sex: str, view: str) -> Image.Image:
    body = silhouette(body_parts(sex, view))
    c = MATERIALS["casquette"]
    r = ramp(c)
    cx = _head_cx(view)
    crown = {q for q in ellipse(cx, 10.2, 6.0, 6.5) if q[1] <= (9 if view == "back" else 8)}
    pieces = [Piece(crown, c)]
    det: dict[Pt, RGB] = {}
    if view == "front":
        pieces.append(Piece(rect(9, 9, 22, 9) | rect(10, 10, 21, 10), darker(c, 0.82)))
        det.update({(15, 6): (236, 228, 208), (16, 6): (236, 228, 208), (15, 7): (236, 228, 208), (16, 7): (200, 190, 170)})
        det.update({(16, y): r[2] for y in (4, 5)})
    elif view == "side":
        pieces.append(Piece(rect(19, 9, 25, 9) | rect(19, 8, 23, 8), darker(c, 0.82)))
        det.update({(19, 6): (236, 228, 208), (19, 7): (200, 190, 170), (14, 5): r[2], (14, 6): r[2], (14, 7): r[2]})
    else:
        det.update({(15, 8): darker(r[3], 0.6), (16, 8): darker(r[3], 0.6), (15, 9): (40, 34, 40), (16, 9): (40, 34, 40)})
        det.update({(16, y): r[2] for y in (4, 5, 6)})
    det.update({(12, 5): r[0], (13, 5): r[0]})
    return render(pieces, body, det)


def draw_hood(sex: str, view: str) -> Image.Image:
    """Capuche de la combinaison : cagoule intégrale, visière et cartouche filtrante."""
    body = silhouette(body_parts(sex, view))
    c = MATERIALS["combi"]
    r, g, k = ramp(c), ramp(MATERIALS["verre"]), ramp(MATERIALS["caoutchouc"])
    cx = _head_cx(view)
    shell = ellipse(cx, 10.6, 6.7, 7.3) | rect(12, 16, 19, 18) | rect(11, 18, 20, 18)
    pieces = [Piece(shell, c)]
    det: dict[Pt, RGB] = {}
    if view == "front":
        glass = rect(12, 9, 19, 13) - {(12, 9), (19, 9), (12, 13), (19, 13)}
        for (x, y) in glass:
            det[(x, y)] = g[2] if (x >= 18 or y == 13) else g[1]
        det.update({(13, 10): g[0], (14, 10): g[0], (13, 11): g[0], (15, 9): g[0], (17, 12): (236, 250, 248)})
        frame = (widen(glass) | {(x, y + d) for (x, y) in glass for d in (-1, 1)}) - glass
        det.update({q: k[1] for q in frame})
        det.update({(15, 15): k[1], (16, 15): k[2], (15, 16): k[2], (16, 16): k[3], (14, 15): k[0], (17, 15): k[3], (15, 14): k[1], (16, 14): k[1]})
        det.update({(11, 16): r[2], (20, 16): r[2]})
    elif view == "side":
        glass = rect(18, 9, 21, 13) - {(21, 9), (21, 13)}
        for (x, y) in glass:
            det[(x, y)] = g[2] if y == 13 else g[1]
        det.update({(18, 10): g[0], (19, 10): g[0], (18, 11): g[0]})
        det.update({(17, y): k[1] for y in range(9, 14)})
        det.update({(x, 8): k[1] for x in range(18, 22)})
        det.update({(x, 14): k[1] for x in range(18, 22)})
        can = rect(20, 15, 23, 17)
        pieces.append(Piece(can, MATERIALS["caoutchouc"]))
        det.update({(13, 12): r[2], (13, 13): r[2], (14, 15): r[2], (15, 16): r[2]})
    else:
        det.update({(16, y): r[2] for y in range(5, 17)})
        det.update({(x, 15): r[2] for x in range(11, 21)})
    det.update({(12, 5): r[0], (13, 4): r[0]})
    return render(pieces, body, det)


def draw_pack(sex: str, view: str) -> Image.Image:
    body = silhouette(body_parts(sex, view))
    c = MATERIALS["sac"]
    r = ramp(c)
    brass = MATERIALS["laiton"]
    det: dict[Pt, RGB] = {}
    if view == "front":  # de face, on ne voit que les bretelles
        straps = rect(12, 18, 13, 26) | rect(18, 18, 19, 26)
        for (x, y) in straps:
            det[(x, y)] = r[2] if x in (13, 19) else r[1]
        det.update({(12, 23): brass, (18, 23): brass})
        return render([], body, det)
    if view == "side":
        bag = (rect(8, 18, 13, 30) - {(8, 18), (8, 30)}) | rect(7, 24, 7, 29)
        det.update({(x, 22): r[3] for x in range(8, 14)})
        det.update({(x, 21): r[0] for x in range(9, 13)})
        det.update({(10, 23): brass, (9, 26): r[2], (10, 26): r[2], (11, 26): r[2], (12, 26): r[2], (9, 29): r[2], (12, 27): r[2], (12, 28): r[2]})
        strap = {(14, 18): r[1], (15, 18): r[1], (16, 18): r[2], (17, 19): r[1], (18, 20): r[1], (19, 21): r[2], (19, 22): r[1], (19, 23): r[1], (19, 24): r[2], (18, 25): r[2]}
        det.update(strap)
        return render([Piece(bag, c)], body, det)
    bag = rect(10, 18, 21, 31) - {(10, 18), (21, 18), (10, 31), (21, 31)}
    det.update({(x, 23): r[3] for x in range(10, 22)})
    det.update({(x, 22): r[2] for x in range(11, 21)})
    det.update({(15, 24): brass, (16, 24): brass, (15, 25): darker(brass, 0.7), (16, 25): darker(brass, 0.7)})
    for x in range(12, 20):  # poche basse
        det[(x, 26)] = r[2]
        det[(x, 30)] = r[2]
    for y in range(26, 31):
        det[(12, y)] = r[2]
        det[(19, y)] = r[3]
    det.update({(13, 27): r[0], (14, 27): r[0], (15, 17): r[2], (16, 17): r[2], (11, 20): r[0], (12, 19): r[0]})
    return render([Piece(bag, c), Piece(rect(15, 16, 16, 17), darker(c, 0.8))], body, det)


# --------------------------------------------------------------------------- catalogue
PIECES = {
    "pantalon_jean": ("pantalon", lambda s, v: draw_pants(s, v, MATERIALS["jean"], MATERIALS["cuir"])),
    "veste_kaki": ("veste", lambda s, v: draw_jacket(s, v, MATERIALS["kaki"], "veste")),
    "casque_militaire": ("tete", draw_helmet),
    "casquette_rouge": ("tete", draw_cap),
    "sac_a_dos": ("dos", draw_pack),
    "combi_capuche": ("tete", draw_hood),
    "combi_haut": ("veste", lambda s, v: draw_jacket(s, v, MATERIALS["combi"], "combi")),
    "combi_bas": ("pantalon", lambda s, v: draw_pants(s, v, MATERIALS["combi"], MATERIALS["caoutchouc"], True, 5, MATERIALS["orange"])),
}
HAIR_STYLES = ("court", "long", "queue")
SLOT_ORDER = ("pantalon", "veste", "cheveux", "tete", "dos")  # du dessous vers le dessus
_VIEW = {"down": "front", "up": "back", "right": "side", "left": "side"}


def sheet(draw) -> Image.Image:
    """Planche 4 directions ; `draw(view)` renvoie un cadre. « left » = miroir de « right »."""
    out = Image.new("RGBA", (FRAME_W * 4, FRAME_H), (0, 0, 0, 0))
    cache: dict[str, Image.Image] = {}
    for i, d in enumerate(DIRECTIONS):
        view = _VIEW[d]
        if view not in cache:
            cache[view] = draw(view)
        frame = ImageOps.mirror(cache[view]) if d == "left" else cache[view]
        out.alpha_composite(frame, (i * FRAME_W, 0))
    return out


def body_sheet(sex: str, skin: str) -> Image.Image:
    return sheet(lambda v: draw_body(sex, v, SKINS[skin]))


def hair_sheet(sex: str, style: str, color: str) -> Image.Image:
    return sheet(lambda v: draw_hair(sex, v, style, HAIR_COLORS[color]))


def piece_sheet(sex: str, name: str) -> Image.Image:
    return sheet(lambda v: PIECES[name][1](sex, v))


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
    for old in out.glob("*.png"):
        old.unlink()
    for sex in "mf":
        for skin in SKINS:
            body_sheet(sex, skin).save(out / f"corps_{sex}_{skin}.png")
        for name in PIECES:
            piece_sheet(sex, name).save(out / f"{name}_{sex}.png")
    for style in HAIR_STYLES:
        for color in HAIR_COLORS:
            hair_sheet("m", style, color).save(out / f"cheveux_{style}_{color}.png")


if __name__ == "__main__":
    main()
