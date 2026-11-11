"""Déplacement partagé serveur/client : constantes, grille de collision et `step()`.

Ce module est la **référence** du déplacement. Le client en possède un port TypeScript
(`client/src/game/movement/`) qui doit produire les mêmes résultats ; les deux sont verrouillés
par `shared/fixtures/movement.json` (généré par `app.zone.movement_fixtures`).

Règles d'écriture, pour que le port soit trivial et bit à bit identique :

- uniquement des opérations IEEE 754 double précision élémentaires (+, −, ×, ÷, `sqrt`,
  `floor`, comparaisons), dans l'ordre exact où elles sont écrites ici ;
- pas de `hypot`, pas de `min`/`max` sur des flottants, pas de fonctions vectorisées ;
- chaque comparaison est documentée (stricte ou non) et doit être recopiée telle quelle.

Unités : tuiles et secondes. Repère : x vers la droite, y vers le bas ; la tuile `(tx, ty)` couvre
`[tx, tx + 1[ × [ty, ty + 1[`. La position d'une entité est le centre de sa boîte AABB.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Fichier de constantes partagé, relatif à la racine du dépôt.
MOVEMENT_FILE = Path("shared/movement/movement.json")
# Racine du dépôt (server/app/zone/movement.py → parents[3]).
REPO_ROOT = Path(__file__).resolve().parents[3]

# Tolérance des tests de recouvrement, en tuiles. Une boîte dont le bord est à moins de EPSILON
# d'une frontière de tuile est considérée comme « au contact » et non « dedans » : le recalage
# exact contre un mur (bord = entier) peut, après arrondi flottant, dépasser l'entier de quelques
# ulps ; sans cette marge, la boîte serait vue à l'intérieur du mur au pas suivant.
EPSILON = 1e-9


@dataclass(frozen=True, slots=True)
class MovementConfig:
    """Constantes de `shared/movement/movement.json`."""

    walk_speed: float
    sprint_speed: float
    player_half_size: float
    max_inputs_per_tick: int
    interest_radius: float

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MovementConfig:
        def number(key: str) -> float:
            value = data[key]
            if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
                raise ValueError(f"movement.json : `{key}` doit être un nombre fini")
            return float(value)

        max_inputs = data["max_inputs_per_tick"]
        if isinstance(max_inputs, bool) or not isinstance(max_inputs, int) or max_inputs < 1:
            raise ValueError("movement.json : `max_inputs_per_tick` doit être un entier ≥ 1")
        config = cls(
            walk_speed=number("walk_speed"),
            sprint_speed=number("sprint_speed"),
            player_half_size=number("player_half_size"),
            max_inputs_per_tick=max_inputs,
            interest_radius=number("interest_radius"),
        )
        if not 0 < config.player_half_size < 0.5:
            # Au-delà de 0,5 la boîte ne passerait plus dans un couloir d'une tuile.
            raise ValueError("movement.json : `player_half_size` doit être dans ]0, 0,5[")
        if config.walk_speed < 0 or config.sprint_speed < 0 or config.interest_radius <= 0:
            raise ValueError("movement.json : vitesses ≥ 0 et rayon d'intérêt > 0 attendus")
        return config

    @classmethod
    def load(cls, path: Path | None = None) -> MovementConfig:
        """Charge le fichier (par défaut celui du dépôt)."""
        source = path if path is not None else REPO_ROOT / MOVEMENT_FILE
        with source.open(encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError(f"{source} : objet JSON attendu")
        return cls.from_dict(data)


class CollisionGrid:
    """Tuiles solides d'une carte. Toute tuile hors carte est solide."""

    __slots__ = ("_solid", "height", "width")

    def __init__(self, width: int, height: int, solid: bytes | bytearray | None = None) -> None:
        if width < 0 or height < 0:
            raise ValueError(f"dimensions de grille invalides : {width} × {height}")
        cells = bytes(solid) if solid is not None else bytes(width * height)
        if len(cells) != width * height:
            raise ValueError("taille du tableau de collision incohérente")
        self.width = width
        self.height = height
        # Une case par tuile, ligne par ligne (index = ty × width + tx) ; non nul = solide.
        self._solid = cells

    @classmethod
    def from_rows(cls, rows: list[str]) -> CollisionGrid:
        """Grille des fixtures : une chaîne par ligne, `#` solide, tout autre caractère libre."""
        height = len(rows)
        width = len(rows[0]) if rows else 0
        cells = bytearray(width * height)
        for ty, row in enumerate(rows):
            if len(row) != width:
                raise ValueError(f"ligne {ty} de longueur {len(row)}, attendu {width}")
            for tx, char in enumerate(row):
                if char == "#":
                    cells[ty * width + tx] = 1
        return cls(width, height, cells)

    def is_solid(self, tx: int, ty: int) -> bool:
        """Vrai si la tuile est solide ou hors carte (`tx < 0`, `ty < 0`, `tx ≥ width`, `ty ≥ height`)."""
        if tx < 0 or ty < 0 or tx >= self.width or ty >= self.height:
            return True
        return self._solid[ty * self.width + tx] != 0

    def any_solid(self, tx0: int, tx1: int, ty0: int, ty1: int) -> bool:
        """Vrai si une tuile du rectangle inclusif `[tx0, tx1] × [ty0, ty1]` est solide."""
        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                if self.is_solid(tx, ty):
                    return True
        return False


@dataclass(frozen=True, slots=True)
class MoveInput:
    """Entrée d'un pas (champs du message `input`, `aim` excepté)."""

    move_x: float
    move_y: float
    sprint: bool


def _clamp_axis(value: float) -> float:
    """Borne un axe à [-1, 1] ; une valeur non finie (NaN, ±inf) vaut 0."""
    if not math.isfinite(value):
        return 0.0
    if value > 1.0:
        return 1.0
    if value < -1.0:
        return -1.0
    return value


def normalize_move(move_x: float, move_y: float) -> tuple[float, float]:
    """Étape 1 : axes bornés à [-1, 1], puis normalisés si la norme dépasse 1.

    La norme est `sqrt(mx * mx + my * my)` (et non `hypot`, dont l'arrondi varie selon les
    moteurs JavaScript). Comparaison **stricte** : `norme² > 1` ; une norme exactement 1 est
    laissée telle quelle. La division se fait axe par axe : `mx / norme`, `my / norme`.
    """
    mx = _clamp_axis(move_x)
    my = _clamp_axis(move_y)
    squared = mx * mx + my * my
    if squared > 1.0:
        norm = math.sqrt(squared)
        mx = mx / norm
        my = my / norm
    return mx, my


def first_tile(low_edge: float) -> int:
    """Première tuile recouverte par une boîte dont le bord bas est `low_edge` : `floor(low_edge + ε)`."""
    return math.floor(low_edge + EPSILON)


def last_tile(high_edge: float) -> int:
    """Dernière tuile recouverte par une boîte dont le bord haut est `high_edge` : `floor(high_edge − ε)`."""
    return math.floor(high_edge - EPSILON)


def overlaps_solid(x: float, y: float, grid: CollisionGrid, half: float) -> bool:
    """Vrai si la boîte de demi-côté `half` centrée en `(x, y)` recouvre une tuile solide (ou hors carte)."""
    tx0, tx1 = first_tile(x - half), last_tile(x + half)
    return grid.any_solid(tx0, tx1, first_tile(y - half), last_tile(y + half))


def _move_axis(center: float, delta: float, half: float, solid_at: Callable[[int], bool]) -> float:
    """Déplace `center` de `delta` sur un axe, contre les tuiles solides.

    `solid_at(i)` dit si la colonne (ou ligne) `i` contient une tuile solide parmi celles que la
    boîte recouvre sur l'autre axe.
    """
    target = center + delta
    if delta > 0.0:
        # Vers les x (ou y) croissants : on balaie les tuiles que le bord haut va franchir, de la
        # plus proche à la plus lointaine. Les tuiles déjà recouvertes au départ sont ignorées
        # (une boîte coincée dans un mur peut toujours en sortir).
        start = last_tile(center + half) + 1
        end = last_tile(target + half)
        for index in range(start, end + 1):
            if solid_at(index):
                # Recalage exact : bord haut = bord bas de la tuile solide.
                return index - half
        return target
    if delta < 0.0:
        # Vers les décroissants : symétrique, sur le bord bas.
        start = first_tile(center - half) - 1
        end = first_tile(target - half)
        for index in range(start, end - 1, -1):
            if solid_at(index):
                # Recalage exact : bord bas = bord haut de la tuile solide (index + 1).
                return (index + 1) + half
        return target
    # delta == 0 (ou NaN, impossible ici) : aucun mouvement.
    return center


def step(
    pos: tuple[float, float], move: MoveInput, grid: CollisionGrid, cfg: MovementConfig, dt: float
) -> tuple[float, float]:
    """Un pas de simulation de durée `dt` secondes. Fonction pure.

    1. `(mx, my) = normalize_move(move_x, move_y)`.
    2. `speed = sprint ? sprint_speed : walk_speed` ; `dx = mx * speed * dt` ; `dy = my * speed * dt`
       (multiplications dans cet ordre, de gauche à droite).
    3. Axe X, à `y` inchangé : lignes recouvertes `ty0 = floor(y − h + ε)` à `ty1 = floor(y + h − ε)`.
       - `dx > 0` : pour `tx` de `floor(x + h − ε) + 1` à `floor(x + dx + h − ε)` (croissant), si une
         tuile `(tx, ty0..ty1)` est solide → `x = tx − h`, arrêt ; sinon `x = x + dx`.
       - `dx < 0` : pour `tx` de `floor(x − h + ε) − 1` à `floor(x + dx − h + ε)` (décroissant), si une
         tuile est solide → `x = (tx + 1) + h`, arrêt ; sinon `x = x + dx`.
       - `dx == 0` : `x` inchangé.
    4. Axe Y de même, avec le **nouveau** `x` : colonnes `floor(x − h + ε)` à `floor(x + h − ε)`.

    `h = player_half_size`, `ε = EPSILON = 1e-9`. Le balayage tuile par tuile empêche de traverser un
    mur quel que soit `dt`. Une tuile hors carte est solide.
    """
    half = cfg.player_half_size
    mx, my = normalize_move(move.move_x, move.move_y)
    speed = cfg.sprint_speed if move.sprint else cfg.walk_speed
    dx = mx * speed * dt
    dy = my * speed * dt
    x, y = pos

    ty0, ty1 = first_tile(y - half), last_tile(y + half)
    x = _move_axis(x, dx, half, lambda tx: grid.any_solid(tx, tx, ty0, ty1))

    tx0, tx1 = first_tile(x - half), last_tile(x + half)
    y = _move_axis(y, dy, half, lambda ty: grid.any_solid(tx0, tx1, ty, ty))
    return x, y
