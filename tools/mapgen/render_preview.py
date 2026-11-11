"""Rendu de contrôle d'une carte Tiled (.tmj) en PNG, comme le client : ground, decor, (joueurs), above.

Usage :
  python3 -I tools/mapgen/render_preview.py maps/valcendre.tmj /tmp/apercu.png
  python3 -I tools/mapgen/render_preview.py maps/valcendre.tmj /tmp/zoom.png --zoom 40 40 40 30 --scale 3
  options : --collision (surimpression rouge des cases solides), --spawns (marque les apparitions)

Nécessite Pillow (outil de développement, pas une dépendance du jeu).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw


def render(
    map_path: Path,
    *,
    collision: bool = False,
    spawns: bool = True,
    zoom: tuple[int, int, int, int] | None = None,
    scale: int = 1,
) -> Image.Image:
    tmj = json.loads(map_path.read_text(encoding="utf-8"))
    ts = tmj["tilesets"][0]
    sheet = Image.open(map_path.parent / ts["image"]).convert("RGBA")
    tw, cols, first = ts["tilewidth"], ts["columns"], ts["firstgid"]
    tiles = [
        sheet.crop(((i % cols) * tw, (i // cols) * tw, (i % cols + 1) * tw, (i // cols + 1) * tw))
        for i in range(ts["tilecount"])
    ]
    w, h = tmj["width"], tmj["height"]
    x0, y0, zw, zh = zoom if zoom else (0, 0, w, h)
    img = Image.new("RGBA", (zw * tw, zh * tw), (0, 0, 0, 255))
    layers = {lyr["name"]: lyr for lyr in tmj["layers"]}

    def draw(name: str) -> None:
        data = layers[name]["data"]
        for y in range(y0, y0 + zh):
            for x in range(x0, x0 + zw):
                g = data[y * w + x]
                if g:
                    img.alpha_composite(tiles[g - first], ((x - x0) * tw, (y - y0) * tw))

    draw("ground")
    draw("decor")
    if spawns:
        d = ImageDraw.Draw(img)
        for obj in layers["spawns"]["objects"]:
            px, py = obj["x"] - x0 * tw, obj["y"] - y0 * tw
            d.ellipse((px - 5, py - 5, px + 5, py + 5), fill=(80, 220, 255, 255), outline=(0, 0, 0, 255))
    draw("above")
    if collision:
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        data = layers["collision"]["data"]
        for y in range(y0, y0 + zh):
            for x in range(x0, x0 + zw):
                if data[y * w + x]:
                    od.rectangle(
                        ((x - x0) * tw, (y - y0) * tw, (x - x0 + 1) * tw - 1, (y - y0 + 1) * tw - 1),
                        fill=(255, 0, 0, 90),
                    )
        img.alpha_composite(overlay)
    if scale != 1:
        img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
    return img


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("map", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--zoom", type=int, nargs=4, metavar=("X", "Y", "W", "H"))
    p.add_argument("--scale", type=int, default=1)
    p.add_argument("--collision", action="store_true")
    p.add_argument("--no-spawns", action="store_true")
    a = p.parse_args()
    img = render(
        a.map.resolve(),
        collision=a.collision,
        spawns=not a.no_spawns,
        zoom=tuple(a.zoom) if a.zoom else None,
        scale=a.scale,
    )
    a.out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(a.out)
    print(f"écrit {a.out} {img.size}")


if __name__ == "__main__":
    main()
