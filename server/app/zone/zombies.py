"""Zombies : apparition et IA, exécutées par le serveur à chaque tick.

États (machine à états finis) :

- `wander`      : erre lentement autour de son point d'origine, avec des pauses ;
- `investigate` : a entendu un bruit, se rend à sa source ;
- `chase`       : a repéré un joueur (vue ou proximité) et le poursuit ; attaque à portée ;
- `search`      : a perdu sa cible de vue, fouille autour de la dernière position connue ;
- `return`      : rentre à son point d'origine (recherche terminée ou trop loin de chez lui) ;
- `dead`        : cadavre, puis réapparition après `respawn_s`.

Perception : vue bloquée par les murs, dans un cône `sight_fov_deg` jusqu'à `sight_range`, ou dans
toutes les directions sous `sense_range`. Une cible déjà poursuivie reste suivie tant qu'elle est en
vue (sans condition de cône), puis encore `CHASE_MEMORY_S` secondes hors de vue.
Ouïe : `hear()` est appelée pour chaque bruit (tirs, coups, pas). Hors de vue, la
poursuite descend un champ de distances (`DistanceField`) pour contourner les murs.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import Literal, Protocol

from app.content.models import ZombieType
from app.protocol.generated import AnimState, EntityState
from app.zone.geometry import DistanceField, angle_diff, line_of_sight
from app.zone.movement import CollisionGrid, MoveInput, MovementConfig, overlaps_solid, step

ZombieState = Literal["wander", "investigate", "chase", "search", "return", "dead"]

# La perception (coûteuse : lignes de vue) n'est évaluée qu'un tick sur `PERCEPTION_EVERY`.
PERCEPTION_EVERY = 4
# Distance à laquelle un but est considéré atteint (tuiles).
ARRIVAL = 0.4
# Sans progression pendant ce temps (s), le zombie abandonne son but.
STUCK_AFTER_S = 1.5
# Durée d'affichage d'un cadavre avant de disparaître des snapshots (s).
CORPSE_S = 8.0
# Une cible qui sort du champ de vision reste poursuivie (à l'odeur, au bruit) pendant ce temps,
# en contournant les obstacles, avant que le zombie passe en recherche.
CHASE_MEMORY_S = 5.0
# Vitesse de l'enquête sur un bruit, relative à la poursuite.
INVESTIGATE_FACTOR = 0.7
# Vitesse du retour, relative à l'errance.
RETURN_FACTOR = 1.5


class Target(Protocol):
    """Ce que l'IA voit d'un joueur vivant."""

    @property
    def key(self) -> str: ...
    @property
    def x(self) -> float: ...
    @property
    def y(self) -> float: ...


@dataclass(slots=True)
class Zombie:
    entity_id: str
    type_id: str
    kind: ZombieType
    home: tuple[float, float]
    x: float
    y: float
    health: float
    aim: float = 0.0
    state: ZombieState = "wander"
    anim: AnimState = "idle"
    target: str | None = None
    goal: tuple[float, float] | None = None
    timer: float = 0.0
    attack_cooldown: float = 0.0
    attack_anim: float = 0.0
    stuck: float = 0.0
    # Poursuite hors de vue : secondes restantes avant d'abandonner (voir CHASE_MEMORY_S).
    memory: float = 0.0
    # Secondes depuis la mort (cadavre puis réapparition).
    dead_for: float = 0.0
    phase: int = 0
    # Dernier attaquant (joueur) : une victime se retourne contre lui.
    provoked_by: str | None = field(default=None)

    @property
    def alive(self) -> bool:
        return self.state != "dead"

    def state_view(self) -> EntityState:
        return EntityState(
            id=self.entity_id,
            kind="zombie",
            name=self.kind.name,
            x=self.x,
            y=self.y,
            aim=self.aim,
            anim=self.anim,
            health=max(0.0, min(1.0, self.health / self.kind.health)),
        )

    def visible(self) -> bool:
        """Vivant, ou cadavre encore affiché."""
        return self.alive or self.dead_for < CORPSE_S

    # --- Événements ---------------------------------------------------------------------------

    def hear(self, x: float, y: float, radius: float) -> bool:
        """Bruit de rayon `radius` en (x, y). Renvoie True s'il est entendu."""
        if not self.alive or self.state == "chase":
            return False
        reach = radius * self.kind.hearing
        if (self.x - x) ** 2 + (self.y - y) ** 2 > reach * reach:
            return False
        self.state = "investigate"
        self.goal = (x, y)
        self.stuck = 0.0
        return True

    def damage(self, amount: float, attacker: str | None) -> bool:
        """Inflige des dégâts ; renvoie True si le coup tue."""
        if not self.alive:
            return False
        self.health -= amount
        if self.health <= 0:
            self.health = 0.0
            self.state = "dead"
            self.anim = "dead"
            self.target = None
            self.dead_for = 0.0
            return True
        if attacker is not None and self.state != "chase":
            self.provoked_by = attacker
        return False

    def respawn(self) -> None:
        self.x, self.y = self.home
        self.health = self.kind.health
        self.state = "wander"
        self.anim = "idle"
        self.goal = None
        self.timer = 0.0
        self.target = None
        self.provoked_by = None


def place_zombies(
    grid: CollisionGrid,
    rng: random.Random,
    type_id: str,
    kind: ZombieType,
    count: int,
    rect: tuple[int, int, int, int],
    *,
    start_index: int,
    avoid: Sequence[tuple[float, float]] = (),
    avoid_radius: float = 0.0,
) -> list[Zombie]:
    """Place `count` zombies sur des tuiles libres du rectangle (x0, x1, y0, y1) inclus."""
    x0, x1, y0, y1 = rect
    free = [
        (tx + 0.5, ty + 0.5)
        for ty in range(y0, y1 + 1)
        for tx in range(x0, x1 + 1)
        if not overlaps_solid(tx + 0.5, ty + 0.5, grid, kind.half_size)
        and all((tx + 0.5 - ax) ** 2 + (ty + 0.5 - ay) ** 2 > avoid_radius**2 for ax, ay in avoid)
    ]
    zombies: list[Zombie] = []
    for i in range(min(count, len(free))):
        x, y = free.pop(rng.randrange(len(free)))
        index = start_index + i
        zombies.append(
            Zombie(
                entity_id=f"z{index}",
                type_id=type_id,
                kind=kind,
                home=(x, y),
                x=x,
                y=y,
                health=kind.health,
                aim=rng.uniform(-math.pi, math.pi),
                phase=index % PERCEPTION_EVERY,
                timer=rng.uniform(0, 4),
            )
        )
    return zombies


class ZombieBrain:
    """IA des zombies d'une zone. Sans état propre hormis les caches de déplacement."""

    def __init__(self, grid: CollisionGrid, movement: MovementConfig, rng: random.Random, dt: float) -> None:
        self.grid = grid
        self.base = movement
        self.rng = rng
        self.dt = dt
        self._configs: dict[tuple[float, float], MovementConfig] = {}

    def _config(self, speed: float, half: float) -> MovementConfig:
        key = (speed, half)
        config = self._configs.get(key)
        if config is None:
            config = replace(self.base, walk_speed=speed, sprint_speed=speed, player_half_size=half)
            self._configs[key] = config
        return config

    # --- Perception ---------------------------------------------------------------------------

    def _sees(self, z: Zombie, t: Target, *, locked: bool) -> bool:
        dx, dy = t.x - z.x, t.y - z.y
        d2 = dx * dx + dy * dy
        k = z.kind
        if d2 > k.sight_range * k.sight_range:
            return False
        if (
            not locked
            and d2 > k.sense_range * k.sense_range
            and angle_diff(math.atan2(dy, dx), z.aim) > math.radians(k.sight_fov_deg) / 2
        ):
            return False
        return line_of_sight(self.grid, z.x, z.y, t.x, t.y)

    def perceive(self, z: Zombie, targets: dict[str, Target], tick: int) -> None:
        if not z.alive:
            return
        if z.provoked_by is not None:
            provoker = targets.get(z.provoked_by)
            z.provoked_by = None
            if provoker is not None:
                self._start_chase(z, provoker)
                return
        if tick % PERCEPTION_EVERY != z.phase:
            return
        if z.state == "chase" and z.target is not None:
            current = targets.get(z.target)
            if current is not None and self._sees(z, current, locked=True):
                z.goal = (current.x, current.y)
                z.memory = CHASE_MEMORY_S
                return
            z.memory -= PERCEPTION_EVERY * self.dt
            if current is not None and z.memory > 0:
                return
            # Cible perdue : on fouille autour de sa dernière position connue.
            z.state = "search"
            z.target = None
            z.timer = z.kind.search_s
            z.stuck = 0.0
            return
        best: Target | None = None
        best_d2 = math.inf
        for t in targets.values():
            d2 = (t.x - z.x) ** 2 + (t.y - z.y) ** 2
            if d2 < best_d2 and self._sees(z, t, locked=False):
                best, best_d2 = t, d2
        if best is not None:
            self._start_chase(z, best)

    @staticmethod
    def _start_chase(z: Zombie, t: Target) -> None:
        z.state = "chase"
        z.target = t.key
        z.goal = (t.x, t.y)
        z.stuck = 0.0
        z.memory = CHASE_MEMORY_S

    # --- Action -------------------------------------------------------------------------------

    def act(
        self,
        z: Zombie,
        targets: dict[str, Target],
        field_for: Callable[[str], DistanceField | None],
        attack: Callable[[Zombie, str], None],
    ) -> None:
        dt = self.dt
        k = z.kind
        z.attack_cooldown = max(0.0, z.attack_cooldown - dt)
        z.attack_anim = max(0.0, z.attack_anim - dt)
        if not z.alive:
            z.dead_for += dt
            return

        if z.state == "chase":
            target = targets.get(z.target) if z.target is not None else None
            if target is None:
                z.state, z.timer = "search", k.search_s
                return
            dx, dy = target.x - z.x, target.y - z.y
            dist = math.sqrt(dx * dx + dy * dy)
            if dist > 1e-9:
                z.aim = math.atan2(dy, dx)
            if (z.x - z.home[0]) ** 2 + (z.y - z.home[1]) ** 2 > k.leash_radius * k.leash_radius:
                z.state, z.target, z.goal = "return", None, z.home
                return
            if dist <= k.attack_range:
                z.anim = "attack" if z.attack_anim > 0 else "idle"
                if z.attack_cooldown <= 0:
                    z.attack_cooldown = k.attack_cooldown_s
                    z.attack_anim = 0.35
                    z.anim = "attack"
                    attack(z, target.key)
                return
            waypoint = (target.x, target.y)
            if not line_of_sight(self.grid, z.x, z.y, target.x, target.y):
                distance_field = field_for(target.key)
                nxt = distance_field.next_tile(math.floor(z.x), math.floor(z.y)) if distance_field else None
                if nxt is not None:
                    waypoint = (nxt[0] + 0.5, nxt[1] + 0.5)
            self._move_towards(z, waypoint, k.chase_speed, run=True)
            if z.attack_anim > 0:
                z.anim = "attack"
            return

        if z.state == "investigate":
            if self._go(z, z.goal or z.home, k.chase_speed * INVESTIGATE_FACTOR):
                z.state, z.timer = "search", k.search_s
            return

        if z.state == "search":
            z.timer -= dt
            if z.timer <= 0:
                z.state, z.goal = "return", z.home
                return
            if z.goal is None or self._go(z, z.goal, k.wander_speed * RETURN_FACTOR):
                angle = self.rng.uniform(-math.pi, math.pi)
                z.goal = (z.x + math.cos(angle) * 2.0, z.y + math.sin(angle) * 2.0)
            return

        if z.state == "return":
            if self._go(z, z.home, k.wander_speed * RETURN_FACTOR, settle=True):
                z.state, z.goal, z.timer = "wander", None, self.rng.uniform(1, 4)
            return

        # Errance : pause, puis un point au hasard autour de l'origine.
        if z.goal is None:
            z.anim = "idle"
            z.timer -= dt
            if z.timer <= 0:
                angle = self.rng.uniform(-math.pi, math.pi)
                radius = self.rng.uniform(0, k.wander_radius)
                z.goal = (z.home[0] + math.cos(angle) * radius, z.home[1] + math.sin(angle) * radius)
            return
        if self._go(z, z.goal, k.wander_speed):
            z.goal = None
            z.timer = self.rng.uniform(2, 6)

    def _go(self, z: Zombie, goal: tuple[float, float], speed: float, *, settle: bool = False) -> bool:
        """Avance vers `goal` ; True si arrivé ou bloqué (abandon). `settle` : un zombie bloqué en
        rentrant s'installe là où il est (nouvelle origine)."""
        if (goal[0] - z.x) ** 2 + (goal[1] - z.y) ** 2 <= ARRIVAL * ARRIVAL:
            z.anim = "idle"
            return True
        moved = self._move_towards(z, goal, speed, run=False)
        if moved:
            z.stuck = 0.0
            return False
        z.stuck += self.dt
        if z.stuck >= STUCK_AFTER_S:
            z.stuck = 0.0
            if settle:
                z.home = (z.x, z.y)
            return True
        return False

    def _move_towards(self, z: Zombie, goal: tuple[float, float], speed: float, *, run: bool) -> bool:
        dx, dy = goal[0] - z.x, goal[1] - z.y
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 1e-9:
            return False
        z.aim = math.atan2(dy, dx)
        # Ne pas dépasser le but en un pas.
        scale = min(1.0, dist / (speed * self.dt)) if speed > 0 else 0.0
        move = MoveInput(dx / dist * scale, dy / dist * scale, False)
        x, y = step((z.x, z.y), move, self.grid, self._config(speed, z.kind.half_size), self.dt)
        moved = abs(x - z.x) + abs(y - z.y) > 1e-6
        z.x, z.y = x, y
        z.anim = ("run" if run else "walk") if moved else "idle"
        return moved
