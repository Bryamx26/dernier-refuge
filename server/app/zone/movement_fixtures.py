"""Générateur de `shared/fixtures/movement.json`, cas de référence de `step()`.

Usage, depuis `server/` :

    uv run python -m app.zone.movement_fixtures           # régénère le fichier
    uv run python -m app.zone.movement_fixtures --check   # échoue si le fichier versionné diffère

Format : une liste de cas
`{name, description, grid: string[] ('#' solide, '.' libre), start: {x, y}, dt, inputs: [{move_x, move_y,
sprint}], expected: [{x, y}, …]}` ; `expected[i]` est la position après l'entrée `i`, chaque pas partant
du résultat du précédent. Les constantes viennent de `shared/movement/movement.json`. Le serveur
(`tests/zone/test_movement.py`) et le client rejouent tous les cas avec une tolérance de 1e-9 tuile.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.zone.movement import MOVEMENT_FILE, REPO_ROOT, CollisionGrid, MoveInput, MovementConfig, step

FIXTURES_FILE = Path("shared/fixtures/movement.json")
DT = 0.05  # 1 / 20 Hz, pas nominal du serveur


@dataclass(frozen=True)
class Case:
    name: str
    description: str
    grid: list[str]
    start: tuple[float, float]
    inputs: list[MoveInput]
    dt: float = DT


def _repeat(move_x: float, move_y: float, count: int, *, sprint: bool = False) -> list[MoveInput]:
    return [MoveInput(move_x, move_y, sprint)] * count


OPEN_8 = ["........"] * 8


def cases() -> list[Case]:
    """Les cas, dans l'ordre du fichier. Ajouter un cas à la fin pour garder les diffs lisibles."""
    return [
        Case("libre_droite", "Marche vers la droite sans obstacle.", OPEN_8, (4.0, 4.0), _repeat(1, 0, 5)),
        Case(
            "libre_gauche_haut",
            "Marche vers la gauche puis vers le haut.",
            OPEN_8,
            (4.5, 4.5),
            _repeat(-1, 0, 3) + _repeat(0, -1, 3),
        ),
        Case("immobile", "Entrée nulle : la position ne change pas.", OPEN_8, (3.25, 2.75), _repeat(0, 0, 3)),
        Case(
            "diagonale_normalisee",
            "(1, 1) est normalisé : même vitesse qu'en ligne droite.",
            OPEN_8,
            (2.0, 2.0),
            _repeat(1, 1, 4),
        ),
        Case(
            "diagonale_partielle",
            "Norme ≤ 1 : pas de normalisation (0,5 ; 0,5), puis norme proche de 1 (0,6 ; 0,8).",
            OPEN_8,
            (2.0, 2.0),
            _repeat(0.5, 0.5, 2) + _repeat(0.6, 0.8, 2) + _repeat(-0.3, 0.7, 2),
        ),
        Case("sprint", "Sprint vers le bas.", OPEN_8, (4.0, 1.0), _repeat(0, 1, 4, sprint=True)),
        Case(
            "mur_droite",
            "Mur sur X (droite) : la boîte s'arrête exactement contre la tuile (x = 5 − 0,3).",
            ["........", "........", ".....#..", ".....#..", ".....#..", "........"],
            (3.5, 3.5),
            _repeat(1, 0, 12),
        ),
        Case(
            "mur_gauche",
            "Mur sur X (gauche) : arrêt à x = 2 + 0,3.",
            ["........", ".#......", ".#......", ".#......", "........"],
            (3.6, 2.5),
            _repeat(-1, 0, 12, sprint=True),
        ),
        Case(
            "mur_bas",
            "Mur sur Y (bas) : arrêt à y = 5 − 0,3.",
            ["......", "......", "......", "......", "......", "######", "......"],
            (2.5, 3.0),
            _repeat(0, 1, 12),
        ),
        Case(
            "mur_haut",
            "Mur sur Y (haut) : arrêt à y = 2 + 0,3.",
            ["......", "######", "......", "......", "......"],
            (3.0, 3.9),
            _repeat(0, -1, 10, sprint=True),
        ),
        Case(
            "coin",
            "Diagonale dans un coin rentrant : bloqué sur les deux axes.",
            ["......#", "......#", "......#", "......#", "#######"],
            (3.0, 1.5),
            _repeat(1, 1, 30),
        ),
        Case(
            "glissement",
            "Diagonale contre un mur vertical : X bloqué, Y continue (glissement).",
            [".....#..", ".....#..", ".....#..", ".....#..", ".....#..", ".....#..", ".....#..", ".....#.."],
            (4.4, 1.0),
            _repeat(1, 1, 10),
        ),
        Case(
            "angle_saillant",
            "Diagonale vers l'angle d'un bloc isolé : X résolu avant Y.",
            ["......", "......", "......", "...#..", "......", "......"],
            (2.2, 2.2),
            _repeat(1, 1, 8),
        ),
        Case(
            "bord_carte",
            "Hors carte = solide : arrêt à 0,3 du bord gauche puis du bord haut.",
            ["....", "....", "...."],
            (1.0, 1.0),
            _repeat(-1, 0, 8) + _repeat(0, -1, 8),
        ),
        Case(
            "bord_carte_bas_droite",
            "Sprint vers le coin bas-droit de la carte.",
            ["....", "....", "...."],
            (2.0, 1.5),
            _repeat(1, 1, 15, sprint=True),
        ),
        Case(
            "entree_hors_bornes",
            "Axes hors de [-1, 1] bornés puis normalisés : (5 ; -3) → (1 ; -1) / √2.",
            OPEN_8,
            (4.0, 4.0),
            [MoveInput(5.0, -3.0, False), MoveInput(-2.5, 0.0, True), MoveInput(0.0, 1e9, False)],
        ),
        Case(
            "couloir",
            "Couloir d'une tuile : la boîte (0,6) passe sans toucher les murs.",
            ["#####", "#...#", "##.##", "##.##", "##.##", "#...#", "#####"],
            (2.5, 1.5),
            _repeat(0, 1, 25),
        ),
        Case(
            "sortie_de_mur",
            "Départ chevauchant un mur : les tuiles déjà recouvertes n'empêchent pas d'en sortir.",
            ["......", "..#...", "......", "......"],
            (2.9, 1.5),
            _repeat(1, 0, 3) + _repeat(-1, 0, 3),
        ),
        Case(
            "grand_dt",
            "dt de 1 s en sprint (5 tuiles) contre un mur fin : pas de traversée.",
            ["..........", "......#...", ".........."],
            (1.5, 1.5),
            [MoveInput(1.0, 0.0, True), MoveInput(-1.0, 0.0, True)],
            dt=1.0,
        ),
    ]


def _number(value: float) -> float | int:
    # Les entiers restent des entiers dans le JSON (plus lisible) ; la valeur est identique.
    return int(value) if float(value).is_integer() and abs(value) < 2**53 else value


def build_fixtures(cfg: MovementConfig) -> list[dict[str, Any]]:
    """Exécute chaque cas avec `step()` et renvoie la structure à écrire."""
    output: list[dict[str, Any]] = []
    for case in cases():
        grid = CollisionGrid.from_rows(case.grid)
        pos = case.start
        expected: list[dict[str, float | int]] = []
        for move in case.inputs:
            pos = step(pos, move, grid, cfg, case.dt)
            expected.append({"x": _number(pos[0]), "y": _number(pos[1])})
        output.append(
            {
                "name": case.name,
                "description": case.description,
                "grid": case.grid,
                "start": {"x": _number(case.start[0]), "y": _number(case.start[1])},
                "dt": case.dt,
                "inputs": [
                    {"move_x": _number(m.move_x), "move_y": _number(m.move_y), "sprint": m.sprint}
                    for m in case.inputs
                ],
                "expected": expected,
            }
        )
    return output


def render(cfg: MovementConfig) -> str:
    """Texte exact du fichier de fixtures (JSON, indentation 2, fin de ligne finale)."""
    return json.dumps(build_fixtures(cfg), indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--check", action="store_true", help="vérifie le fichier au lieu de l'écrire")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="racine du dépôt")
    args = parser.parse_args(argv)

    text = render(MovementConfig.load(args.root / MOVEMENT_FILE))
    target: Path = args.root / FIXTURES_FILE
    if args.check:
        current = target.read_text(encoding="utf-8") if target.exists() else ""
        if current != text:
            print(f"{target} n'est pas à jour : relancer sans --check", file=sys.stderr)
            return 1
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    print(f"{target} écrit ({len(cases())} cas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
