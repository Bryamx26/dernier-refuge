"""Géométrie sur la grille de collision : ligne de vue, lancer de rayon, champ de distances.

Utilisé par l'IA des zombies (vue, poursuite) et le combat (tirs). Unités : tuiles.
"""

from __future__ import annotations

import math
from collections import deque

from app.zone.movement import CollisionGrid

# Pas maximal du parcours de tuiles (sécurité contre une boucle infinie).
_MAX_STEPS = 4096


def raycast(grid: CollisionGrid, x: float, y: float, dx: float, dy: float, max_dist: float) -> float:
    """Distance parcourue depuis (x, y) dans la direction unitaire (dx, dy) avant la première tuile
    solide, bornée à `max_dist`. Parcours exact des tuiles traversées (DDA d'Amanatides et Woo)."""
    tx, ty = math.floor(x), math.floor(y)
    if grid.is_solid(tx, ty):
        return 0.0
    step_x = 1 if dx > 0 else -1
    step_y = 1 if dy > 0 else -1
    t_delta_x = abs(1.0 / dx) if dx != 0 else math.inf
    t_delta_y = abs(1.0 / dy) if dy != 0 else math.inf
    t_max_x = ((tx + 1 - x) if dx > 0 else (x - tx)) * t_delta_x if dx != 0 else math.inf
    t_max_y = ((ty + 1 - y) if dy > 0 else (y - ty)) * t_delta_y if dy != 0 else math.inf
    for _ in range(_MAX_STEPS):
        if t_max_x < t_max_y:
            t = t_max_x
            tx += step_x
            t_max_x += t_delta_x
        else:
            t = t_max_y
            ty += step_y
            t_max_y += t_delta_y
        if t >= max_dist:
            return max_dist
        if grid.is_solid(tx, ty):
            return t
    return max_dist


def line_of_sight(grid: CollisionGrid, x0: float, y0: float, x1: float, y1: float) -> bool:
    """Vrai si le segment (x0, y0) → (x1, y1) ne traverse aucune tuile solide."""
    dist = math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2)
    if dist < 1e-9:
        return not grid.is_solid(math.floor(x0), math.floor(y0))
    return raycast(grid, x0, y0, (x1 - x0) / dist, (y1 - y0) / dist, dist) >= dist


def angle_diff(a: float, b: float) -> float:
    """Écart absolu entre deux angles, dans [0, π]."""
    d = (a - b) % (2 * math.pi)
    return 2 * math.pi - d if d > math.pi else d


class DistanceField:
    """Distances (en pas de 4-voisinage) vers une tuile cible, dans un carré de rayon `radius`.

    Calculé par parcours en largeur ; sert aux zombies qui poursuivent une cible hors de vue :
    ils descendent le champ vers la cible en contournant les bâtiments.
    """

    __slots__ = ("_dist", "origin", "radius", "x0", "y0")

    def __init__(self, grid: CollisionGrid, tx: int, ty: int, radius: int) -> None:
        self.origin = (tx, ty)
        self.radius = radius
        self.x0, self.y0 = tx - radius, ty - radius
        side = 2 * radius + 1
        dist = [-1] * (side * side)
        self._dist = dist
        if grid.is_solid(tx, ty):
            return
        dist[radius * side + radius] = 0
        queue: deque[tuple[int, int]] = deque([(tx, ty)])
        while queue:
            cx, cy = queue.popleft()
            d = dist[(cy - self.y0) * side + (cx - self.x0)] + 1
            for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                lx, ly = nx - self.x0, ny - self.y0
                if lx < 0 or ly < 0 or lx >= side or ly >= side:
                    continue
                index = ly * side + lx
                if dist[index] != -1 or grid.is_solid(nx, ny):
                    continue
                dist[index] = d
                queue.append((nx, ny))

    def distance(self, tx: int, ty: int) -> int:
        """Distance de la tuile à la cible, -1 si inaccessible ou hors du champ."""
        lx, ly = tx - self.x0, ty - self.y0
        side = 2 * self.radius + 1
        if lx < 0 or ly < 0 or lx >= side or ly >= side:
            return -1
        return self._dist[ly * side + lx]

    def next_tile(self, tx: int, ty: int) -> tuple[int, int] | None:
        """Tuile voisine qui rapproche de la cible, ou None (déjà sur la cible, ou hors du champ)."""
        here = self.distance(tx, ty)
        if here <= 0:
            return None
        best: tuple[int, int] | None = None
        best_d = here
        for nx, ny in ((tx + 1, ty), (tx - 1, ty), (tx, ty + 1), (tx, ty - 1)):
            d = self.distance(nx, ny)
            if 0 <= d < best_d:
                best, best_d = (nx, ny), d
        return best
