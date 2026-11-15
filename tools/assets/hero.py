"""Survivant dessiné à la main, pixel par pixel (création originale, aucun asset externe).

La grille ci-dessous EST le dessin : une lettre = un pixel, la palette donne sa couleur.
Changer la palette donne d'autres personnages (cheveux, peau, veste...) sans redessiner.

Usage : `python3 -I tools/assets/hero.py` → assets/characters/hero/survivant*.png
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

GRID = """
......oooooooo......
....oohhHHHHhhoo....
...ohhHHHHHHHhhho...
..ohhHHHhhhhHHhhdo..
..ohHHhhhhhhhhhhdo..
..ohhhhssSSsshhhdo..
..ohhsSSSSSSSsshdo..
..odhsSeSSSSeSthdo..
..odhsSeSSSSeSthdo..
..odhsSSSSSSSSthdo..
...odsSSSttSSStdo...
....oottSSSSttoo....
..oooJJrrttrrJJooo..
.oJJJjrRRRRRRrjjjko.
.oJJkjmJJjkjjmjkjko.
.oJjkjmJjjkjjmjkjko.
.oJjkjmjjjkjjmjkjko.
.oJjkjnjjjkjjnjkjko.
.oJjkjjjjjkjjjjkjko.
.ojjknnnnnMnnnnkjko.
.osSopPPppqppppoSto.
.ostopPPppqppppotto.
..ooopPppqqppppooo..
....opPppqqppppo....
....opPppqqppppo....
....opPpqoopppqo....
....opPpqoopppqo....
....obBbcoobbbco....
....obBbcoobbbco....
...obBbbcoobbbbco...
...occcccooccccco...
....ooooo..ooooo....
"""

PALETTE = {
    "o": (31, 26, 36),
    "h": (107, 74, 47), "H": (143, 106, 67), "d": (70, 48, 31),
    "s": (232, 184, 143), "S": (246, 210, 173), "t": (196, 143, 104),
    "e": (42, 37, 48),
    "j": (111, 128, 72), "J": (143, 160, 94), "k": (79, 94, 54),
    "r": (179, 68, 58), "R": (208, 96, 79),
    "p": (74, 90, 120), "P": (98, 116, 154), "q": (53, 66, 92),
    "b": (106, 70, 48), "B": (138, 96, 64), "c": (72, 48, 31),
    "m": (160, 122, 72), "n": (122, 90, 52), "M": (222, 186, 96),
}

# Variantes par simple changement de palette (mêmes pixels).
VARIANTS = {
    "survivant": {},
    "survivant_b": {  # peau foncée, cheveux noirs, veste bleu nuit, écharpe jaune
        "h": (52, 46, 54), "H": (78, 70, 82), "d": (34, 30, 38),
        "s": (150, 102, 70), "S": (176, 126, 90), "t": (118, 78, 54),
        "j": (62, 80, 110), "J": (84, 106, 140), "k": (44, 58, 84),
        "r": (206, 160, 60), "R": (232, 192, 92),
        "p": (86, 80, 72), "P": (112, 104, 94), "q": (62, 58, 52),
    },
    "survivant_c": {  # rousse, peau claire, veste bordeaux, écharpe sarcelle
        "h": (176, 84, 40), "H": (212, 120, 60), "d": (124, 56, 28),
        "j": (132, 62, 62), "J": (164, 86, 82), "k": (96, 44, 48),
        "r": (60, 140, 136), "R": (92, 176, 168),
        "p": (64, 70, 64), "P": (86, 94, 86), "q": (46, 52, 48),
    },
}


def rows() -> list[str]:
    lines = GRID.strip("\n").split("\n")
    assert all(len(r) == 20 for r in lines), [(i, len(r)) for i, r in enumerate(lines) if len(r) != 20]
    return lines


def draw(palette: dict[str, tuple[int, int, int]]) -> Image.Image:
    lines = rows()
    img = Image.new("RGBA", (20, len(lines)), (0, 0, 0, 0))
    for y, line in enumerate(lines):
        for x, ch in enumerate(line):
            if ch != ".":
                img.putpixel((x, y), (*palette[ch], 255))
    return img


def variant(name: str) -> Image.Image:
    return draw({**PALETTE, **VARIANTS[name]})


def main() -> None:
    out = Path(__file__).resolve().parents[2] / "assets" / "characters" / "hero"
    out.mkdir(parents=True, exist_ok=True)
    for name in VARIANTS:
        variant(name).save(out / f"{name}.png")


if __name__ == "__main__":
    main()
