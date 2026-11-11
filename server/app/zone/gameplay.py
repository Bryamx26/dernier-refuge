"""Règles de jeu d'une zone (phase 3) : zombies, combat, inventaire, fouille, survie.

`ZoneRuntime` reste responsable du réseau, du déplacement et des sessions ; il appelle ici :

- `on_input` pour chaque entrée appliquée (gâchette, annulation d'une fouille si le joueur bouge) ;
- `on_action` pour chaque message `action` (ramasser/fouiller, utiliser, jeter, recharger, réapparaître) ;
- `tick` une fois par tick (actions longues, survie, bruits, IA des zombies, réapparitions).

Toutes les valeurs de jeu viennent de `content/` (`GameContent`). Le hasard passe par `self.rng`
(injectable : tests déterministes).
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from app.content.loader import GameContent
from app.content.models import FirearmStats, ItemDef, MeleeStats, ZonePopulation
from app.protocol.generated import ActionPayload, EntityState, FxEvent, FxKind, InputPayload, VitalsPayload
from app.zone.geometry import DistanceField, angle_diff, raycast
from app.zone.inventory import Inventory, ItemStack, new_stack
from app.zone.loot import Building, GroundItem, roll_loot
from app.zone.movement import MovementConfig, overlaps_solid
from app.zone.survival import Vitals
from app.zone.tilemap import ZoneMap
from app.zone.zombies import Zombie, ZombieBrain, place_zombies

if TYPE_CHECKING:
    from app.zone.runtime import PlayerEntity

# Distance de ramassage d'un objet au sol (tuiles).
PICKUP_RANGE = 1.3
# Durée de vie d'un objet au sol (s).
GROUND_ITEM_S = 900.0
# Rayon du champ de distances de poursuite (tuiles) et période de recalcul (ticks).
FIELD_RADIUS = 24
FIELD_REFRESH_TICKS = 10
# Période des bruits de pas (ticks) et des messages `vitals` sans changement.
FOOTSTEP_EVERY = 10
VITALS_EVERY = 10
# Rayon des cibles pour les tirs (tuiles), ajouté à la demi-taille du zombie.
HIT_MARGIN = 0.1
# Les cadavres et les réapparitions sont réévalués une fois par seconde.
RESPAWN_CHECK_EVERY = 20


@dataclass(slots=True)
class LongAction:
    kind: Literal["search", "reload"]
    label: str
    started: int
    ends: int
    building: Building | None = None


@dataclass(slots=True)
class Survivor:
    """État de jeu d'un personnage connecté."""

    vitals: Vitals
    inventory: Inventory
    # Tick à partir duquel l'arme peut de nouveau frapper/tirer.
    ready_at: int = 0
    action: LongAction | None = None
    vitals_dirty: bool = True
    inventory_dirty: bool = True
    notices: list[str] = field(default_factory=list)
    # La mort a déjà été traitée (inventaire lâché).
    death_handled: bool = False
    # Gâchette tenue au pas précédent (pour ne signaler un chargeur vide qu'une fois par pression).
    trigger_held: bool = False

    def notify(self, text: str) -> None:
        self.notices.append(text[:120])


@dataclass(frozen=True, slots=True)
class _TargetView:
    """Joueur vivant vu par l'IA des zombies."""

    key: str
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class PositionedFx:
    event: FxEvent

    @property
    def x(self) -> float:
        return self.event.x

    @property
    def y(self) -> float:
        return self.event.y


class Gameplay:
    def __init__(
        self,
        content: GameContent,
        zone_map: ZoneMap,
        movement: MovementConfig,
        *,
        tick_rate: int,
        population: ZonePopulation | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self.content = content
        self.map = zone_map
        self.movement = movement
        self.tick_rate = tick_rate
        self.dt = 1.0 / tick_rate
        self.population = population
        self.rng = rng if rng is not None else random.Random()
        self.tick_count = 0
        self.zombies: list[Zombie] = []
        self.ground: dict[str, GroundItem] = {}
        self._ground_counter = 0
        self.buildings = [
            Building(info=b, table=content.loot.buildings.get(b.name, "default")) for b in zone_map.buildings
        ]
        # Effets du tick ; vidés par la zone après envoi (`ZoneRuntime._send_game_messages`).
        self.fx: list[PositionedFx] = []
        self._noises: list[tuple[float, float, float]] = []
        self._fields: dict[str, tuple[int, DistanceField]] = {}
        self.brain = ZombieBrain(zone_map.grid, movement, self.rng, self.dt)
        if population is not None:
            self._populate(population)

    # --- Mise en place ---------------------------------------------------------------------------

    def _populate(self, population: ZonePopulation) -> None:
        placement_rng = random.Random(population.seed)
        for group in population.zombie_groups:
            kind = self.content.zombies.types[group.type]
            self.zombies.extend(
                place_zombies(
                    self.map.grid,
                    placement_rng,
                    group.type,
                    kind,
                    group.count,
                    (group.x0, group.x1, group.y0, group.y1),
                    start_index=len(self.zombies) + 1,
                    avoid=self.map.spawns,
                    avoid_radius=8.0,
                )
            )

    def ticks(self, seconds: float) -> int:
        return max(1, round(seconds * self.tick_rate))

    def new_survivor(self, saved_inventory: object | None = None, vitals: Vitals | None = None) -> Survivor:
        """Survivant chargé de la base (`saved_inventory` déjà décodé) ou neuf (équipement de départ)."""
        config = self.content.survival
        inventory = Inventory(self.content.items.items, config.inventory_slots, config.max_weight)
        if saved_inventory is None:
            self._give_starter_kit(inventory)
        else:
            inventory.load_json(saved_inventory)
        return Survivor(vitals=vitals if vitals is not None else Vitals.fresh(config), inventory=inventory)

    def _give_starter_kit(self, inventory: Inventory) -> None:
        for starter in self.content.survival.starter_kit:
            item = self.content.items.items[starter.item]
            inventory.add(new_stack(starter.item, item, starter.qty))
        # L'arme de départ est en main.
        for index, stack in sorted(inventory.slots.items()):
            if self.content.items.items[stack.item].kind in ("melee", "firearm"):
                inventory.equipped = index
                break

    def random_spawn(self, half: float) -> tuple[float, float]:
        """Point d'apparition libre tiré au hasard (QA-P2-03 : les nouveaux joueurs ne s'empilent plus)."""
        free = [s for s in self.map.spawns if not overlaps_solid(s[0], s[1], self.map.grid, half)]
        if free:
            return self.rng.choice(free)
        return self.map.resolve_spawn(None, half)

    # --- Entrées ---------------------------------------------------------------------------------

    def on_input(self, player: PlayerEntity, payload: InputPayload, moved: bool) -> None:
        """Appelé pour chaque entrée appliquée au joueur (après son déplacement)."""
        s = player.survivor
        if s.vitals.dead:
            return
        if moved and s.action is not None and s.action.kind == "search":
            s.action = None
            s.vitals_dirty = True
            s.notify("Fouille interrompue")
        if payload.attack:
            self._attack(player, first_press=not s.trigger_held)
        s.trigger_held = payload.attack

    def on_action(self, player: PlayerEntity, action: ActionPayload) -> None:
        s = player.survivor
        if action.kind == "respawn":
            if s.vitals.dead:
                self.respawn(player)
            return
        if s.vitals.dead:
            return
        if action.kind == "interact":
            self._interact(player)
        elif action.kind == "use":
            self._use(player, action.slot)
        elif action.kind == "drop":
            self._drop(player, action.slot)
        elif action.kind == "reload":
            self._start_reload(player)

    # --- Combat ----------------------------------------------------------------------------------

    def _weapon(
        self, s: Survivor
    ) -> tuple[ItemStack | None, ItemDef | None, MeleeStats | None, FirearmStats | None]:
        stack = s.inventory.equipped_stack()
        if stack is not None:
            item = self.content.items.items[stack.item]
            if item.melee is not None or item.firearm is not None:
                return stack, item, item.melee, item.firearm
        return None, None, self.content.items.unarmed.melee, None

    def _attack(self, player: PlayerEntity, *, first_press: bool) -> None:
        s = player.survivor
        if self.tick_count < s.ready_at:
            return
        if s.action is not None:
            if s.action.kind == "reload":
                return
            s.action = None
            s.vitals_dirty = True
        stack, item, melee, firearm = self._weapon(s)
        if firearm is not None and stack is not None and item is not None:
            if stack.loaded <= 0:
                if first_press:
                    s.notify("Chargeur vide : R pour recharger")
                    s.ready_at = self.tick_count + self.ticks(0.3)
                return
            stack.loaded -= 1
            s.ready_at = self.tick_count + self.ticks(firearm.cooldown_s)
            self._fire(player, firearm)
            self._wear(s, stack, item)
            s.inventory_dirty = True
        elif melee is not None:
            s.ready_at = self.tick_count + self.ticks(melee.cooldown_s)
            hit = self._swing(player, melee)
            if hit and stack is not None and item is not None:
                self._wear(s, stack, item)
                s.inventory_dirty = True

    def _wear(self, s: Survivor, stack: ItemStack, item: ItemDef) -> None:
        stack.durability -= 1
        if stack.durability <= 0:
            slot = s.inventory.equipped
            s.inventory.take(slot, stack.qty)
            s.notify(f"{item.name} : cassé")

    def _swing(self, player: PlayerEntity, melee: MeleeStats) -> bool:
        """Coup de mêlée : touche le zombie vivant le plus proche dans l'arc. Renvoie True si touché."""
        reach = melee.range
        half_arc = math.radians(melee.arc_deg) / 2
        best: Zombie | None = None
        best_d = math.inf
        for z in self.zombies:
            if not z.alive:
                continue
            dx, dy = z.x - player.x, z.y - player.y
            d = math.sqrt(dx * dx + dy * dy)
            if d > reach + z.kind.half_size or d >= best_d:
                continue
            if d > 1e-9 and angle_diff(math.atan2(dy, dx), player.aim) > half_arc:
                continue
            best, best_d = z, d
        tip = (player.x + math.cos(player.aim) * reach, player.y + math.sin(player.aim) * reach)
        self._emit("swing", player.x, player.y, tip[0], tip[1])
        self._noise(player.x, player.y, melee.noise)
        if best is None:
            return False
        best.damage(melee.damage, player.character_id)
        self._emit("hit", best.x, best.y)
        return True

    def _fire(self, player: PlayerEntity, firearm: FirearmStats) -> None:
        spread = math.radians(firearm.spread_deg)
        for _ in range(firearm.pellets):
            angle = player.aim + self.rng.uniform(-spread / 2, spread / 2)
            dx, dy = math.cos(angle), math.sin(angle)
            limit = raycast(self.map.grid, player.x, player.y, dx, dy, firearm.range)
            victim: Zombie | None = None
            for z in self.zombies:
                if not z.alive:
                    continue
                t = _ray_circle(player.x, player.y, dx, dy, z.x, z.y, z.kind.half_size + HIT_MARGIN)
                if t is not None and t < limit:
                    victim, limit = z, t
            end = (player.x + dx * limit, player.y + dy * limit)
            self._emit("shot", player.x, player.y, end[0], end[1])
            if victim is not None:
                victim.damage(firearm.damage, player.character_id)
                self._emit("hit", end[0], end[1])
        self._noise(player.x, player.y, firearm.noise)

    def _start_reload(self, player: PlayerEntity) -> None:
        s = player.survivor
        stack, item, _, firearm = self._weapon(s)
        if firearm is None or stack is None or item is None:
            s.notify("Aucune arme à feu en main")
            return
        if s.action is not None:
            return
        if stack.loaded >= firearm.magazine:
            s.notify("Chargeur plein")
            return
        if s.inventory.count(firearm.ammo) == 0:
            s.notify(f"Plus de munitions ({self.content.items.items[firearm.ammo].name})")
            return
        s.action = LongAction(
            kind="reload",
            label="Rechargement",
            started=self.tick_count,
            ends=self.tick_count + self.ticks(firearm.reload_s),
        )
        s.vitals_dirty = True

    def _finish_reload(self, s: Survivor) -> None:
        stack, _, _, firearm = self._weapon(s)
        if firearm is None or stack is None:
            return
        taken = s.inventory.consume(firearm.ammo, firearm.magazine - stack.loaded)
        stack.loaded += taken
        s.inventory_dirty = True

    # --- Objets et fouille -----------------------------------------------------------------------

    def _interact(self, player: PlayerEntity) -> None:
        s = player.survivor
        if s.action is not None:
            return
        nearest: GroundItem | None = None
        best = PICKUP_RANGE * PICKUP_RANGE
        for g in self.ground.values():
            d2 = (g.x - player.x) ** 2 + (g.y - player.y) ** 2
            if d2 <= best:
                nearest, best = g, d2
        if nearest is not None:
            self._pick_up(s, nearest)
            return
        loot = self.content.loot
        for building in self.buildings:
            cx, cy = building.door_center
            if (cx - player.x) ** 2 + (cy - player.y) ** 2 > loot.search_range**2:
                continue
            if self.tick_count < building.restocked_at:
                s.notify(f"{building.info.name} : déjà fouillé, rien de plus pour l'instant")
                return
            s.action = LongAction(
                kind="search",
                label=f"Fouille : {building.info.name}"[:48],
                started=self.tick_count,
                ends=self.tick_count + self.ticks(loot.search_s),
                building=building,
            )
            s.vitals_dirty = True
            self._emit("search", cx, cy)
            return
        s.notify("Rien à ramasser ni à fouiller ici")

    def _pick_up(self, s: Survivor, ground: GroundItem) -> None:
        item = self.content.items.items[ground.stack.item]
        left = s.inventory.add(ground.stack)
        taken = ground.stack.qty - left
        if taken == 0:
            s.notify("Inventaire plein ou trop lourd")
            return
        s.inventory_dirty = True
        if left == 0:
            del self.ground[ground.entity_id]
        else:
            ground.stack.qty = left
        s.notify(f"Ramassé : {item.name}" + (f" × {taken}" if taken > 1 else ""))

    def _finish_search(self, player: PlayerEntity, building: Building) -> None:
        s = player.survivor
        if self.tick_count < building.restocked_at:
            s.notify(f"{building.info.name} : quelqu'un est passé avant vous")
            return
        building.restocked_at = self.tick_count + self.ticks(self.content.loot.restock_s)
        found = roll_loot(self.content.loot, building.table, self.content.items.items, self.rng)
        if not found:
            s.notify(f"{building.info.name} : rien trouvé")
            return
        names: list[str] = []
        dropped = 0
        for stack in found:
            left = s.inventory.add(stack)
            name = self.content.items.items[stack.item].name
            names.append(name if stack.qty == 1 else f"{name} × {stack.qty}")
            if left > 0:
                dropped += 1
                self.drop_on_ground(
                    ItemStack(stack.item, left, stack.durability, stack.loaded), player.x, player.y
                )
        s.inventory_dirty = True
        text = "Trouvé : " + ", ".join(names)
        if dropped:
            text += " (trop chargé : posé au sol)"
        s.notify(text)

    def drop_on_ground(self, stack: ItemStack, x: float, y: float) -> GroundItem:
        self._ground_counter += 1
        angle = self.rng.uniform(-math.pi, math.pi)
        radius = self.rng.uniform(0.0, 0.5)
        gx, gy = x + math.cos(angle) * radius, y + math.sin(angle) * radius
        if overlaps_solid(gx, gy, self.map.grid, 0.2):
            gx, gy = x, y
        ground = GroundItem(
            entity_id=f"i{self._ground_counter}",
            stack=stack,
            x=gx,
            y=gy,
            expires_at=self.tick_count + self.ticks(GROUND_ITEM_S),
        )
        self.ground[ground.entity_id] = ground
        return ground

    def _use(self, player: PlayerEntity, slot: int) -> None:
        s = player.survivor
        stack = s.inventory.slots.get(slot)
        if stack is None:
            return
        item = self.content.items.items[stack.item]
        if item.melee is not None or item.firearm is not None:
            if s.action is not None and s.action.kind == "reload":
                s.action = None
                s.vitals_dirty = True
            s.inventory.equipped = -1 if s.inventory.equipped == slot else slot
            s.inventory_dirty = True
            return
        if item.consume is not None:
            s.vitals.apply(item.consume, self.content.survival)
            s.inventory.take(slot, 1)
            s.inventory_dirty = True
            s.vitals_dirty = True
            s.notify(f"Utilisé : {item.name}")
            return
        s.notify(f"{item.name} : se charge dans une arme (R)")

    def _drop(self, player: PlayerEntity, slot: int) -> None:
        s = player.survivor
        stack = s.inventory.slots.get(slot)
        if stack is None:
            return
        if s.action is not None and s.action.kind == "reload" and slot == s.inventory.equipped:
            s.action = None
            s.vitals_dirty = True
        taken = s.inventory.take(slot, stack.qty)
        if taken is not None:
            self.drop_on_ground(taken, player.x, player.y)
            s.inventory_dirty = True

    # --- Mort et réapparition --------------------------------------------------------------------

    def _die(self, player: PlayerEntity) -> None:
        s = player.survivor
        s.death_handled = True
        s.action = None
        s.vitals.bleeding = False
        for stack in s.inventory.clear():
            self.drop_on_ground(stack, player.x, player.y)
        s.inventory_dirty = True
        s.vitals_dirty = True
        player.anim = "dead"
        self._emit("blood", player.x, player.y)
        s.notify("Vous êtes mort. Vos affaires sont restées sur place.")

    def respawn(self, player: PlayerEntity) -> None:
        s = player.survivor
        s.vitals = Vitals.fresh(self.content.survival)
        s.inventory.clear()
        self._give_starter_kit(s.inventory)
        s.death_handled = False
        s.action = None
        s.ready_at = 0
        s.vitals_dirty = True
        s.inventory_dirty = True
        player.x, player.y = self.random_spawn(self.movement.player_half_size)
        player.anim = "idle"
        s.notify("Nouveau départ. Bonne chance.")

    # --- Tick ------------------------------------------------------------------------------------

    def tick(self, players: dict[str, PlayerEntity]) -> None:
        self.tick_count += 1
        survival = self.content.survival
        noise = self.content.zombies.player_noise
        targets: dict[str, _TargetView] = {}
        for player in players.values():
            s = player.survivor
            before = (round(s.vitals.health), s.vitals.bleeding)
            s.vitals.tick(survival, self.dt)
            if (round(s.vitals.health), s.vitals.bleeding) != before:
                s.vitals_dirty = True
            if s.vitals.dead:
                if not s.death_handled:
                    self._die(player)
                player.anim = "dead"
                continue
            if s.action is not None and self.tick_count >= s.action.ends:
                action, s.action = s.action, None
                s.vitals_dirty = True
                if action.kind == "reload":
                    self._finish_reload(s)
                elif action.building is not None:
                    self._finish_search(player, action.building)
            if self.tick_count % FOOTSTEP_EVERY == 0 and player.anim in ("walk", "run"):
                self._noise(player.x, player.y, noise.sprint if player.anim == "run" else noise.walk)
            targets[player.character_id] = _TargetView(player.character_id, player.x, player.y)

        for x, y, radius in self._noises:
            for z in self.zombies:
                z.hear(x, y, radius)
        self._noises.clear()

        def attack(zombie: Zombie, key: str) -> None:
            victim = players.get(key)
            if victim is None or victim.survivor.vitals.dead:
                return
            v = victim.survivor
            v.vitals.hurt(zombie.kind.attack_damage)
            if self.rng.random() < zombie.kind.bleed_chance and not v.vitals.bleeding:
                v.vitals.bleeding = True
                v.notify("Vous saignez : utilisez un bandage")
            v.vitals_dirty = True
            self._emit("blood", victim.x, victim.y)

        for z in self.zombies:
            self.brain.perceive(z, targets, self.tick_count)  # type: ignore[arg-type]
            self.brain.act(z, targets, lambda key: self._field(key, targets), attack)  # type: ignore[arg-type]

        if self.tick_count % RESPAWN_CHECK_EVERY == 0:
            self._respawn_zombies(players)
            expired = [k for k, g in self.ground.items() if g.expires_at <= self.tick_count]
            for key in expired:
                del self.ground[key]

    def _field(self, key: str, targets: dict[str, _TargetView]) -> DistanceField | None:
        target = targets.get(key)
        if target is None:
            return None
        tile = (math.floor(target.x), math.floor(target.y))
        cached = self._fields.get(key)
        if cached is not None:
            computed_at, distance_field = cached
            if distance_field.origin == tile or self.tick_count - computed_at < FIELD_REFRESH_TICKS:
                return distance_field
        distance_field = DistanceField(self.map.grid, tile[0], tile[1], FIELD_RADIUS)
        self._fields[key] = (self.tick_count, distance_field)
        return distance_field

    def _respawn_zombies(self, players: dict[str, PlayerEntity]) -> None:
        population = self.population
        if population is None:
            return
        min_d2 = population.respawn_min_player_distance**2
        for z in self.zombies:
            if z.alive or z.dead_for < population.respawn_s:
                continue
            hx, hy = z.home
            if all((p.x - hx) ** 2 + (p.y - hy) ** 2 >= min_d2 for p in players.values()):
                z.respawn()

    # --- Sorties ---------------------------------------------------------------------------------

    def _emit(
        self, kind: FxKind, x: float, y: float, x2: float | None = None, y2: float | None = None
    ) -> None:
        self.fx.append(
            PositionedFx(FxEvent(kind=kind, x=x, y=y, x2=x if x2 is None else x2, y2=y if y2 is None else y2))
        )

    def _noise(self, x: float, y: float, radius: float) -> None:
        if radius > 0:
            self._noises.append((x, y, radius))

    def world_entities(self) -> Iterator[tuple[float, float, EntityState]]:
        """Zombies visibles et objets au sol, avec leur position (pour le filtre d'intérêt)."""
        for z in self.zombies:
            if z.visible():
                yield z.x, z.y, z.state_view()
        for g in self.ground.values():
            item = self.content.items.items[g.stack.item]
            name = item.name if g.stack.qty == 1 else f"{item.name} × {g.stack.qty}"
            yield (
                g.x,
                g.y,
                EntityState(
                    id=g.entity_id,
                    kind="item",
                    name=name[:32],
                    x=g.x,
                    y=g.y,
                    aim=0.0,
                    anim="idle",
                    health=1.0,
                ),
            )

    def vitals_payload(self, s: Survivor) -> VitalsPayload:
        v = s.vitals
        action, progress = "", 0.0
        if s.action is not None:
            span = max(1, s.action.ends - s.action.started)
            action = s.action.label
            progress = min(1.0, max(0.0, (self.tick_count - s.action.started) / span))
        return VitalsPayload(
            health=round(v.health, 2),
            max_health=self.content.survival.max_health,
            hunger=round(v.hunger, 2),
            thirst=round(v.thirst, 2),
            bleeding=v.bleeding,
            dead=v.dead,
            action=action,
            action_progress=round(progress, 3),
        )


def _ray_circle(ox: float, oy: float, dx: float, dy: float, cx: float, cy: float, r: float) -> float | None:
    """Distance le long du rayon (origine o, direction unitaire d) jusqu'au cercle, ou None."""
    fx, fy = ox - cx, oy - cy
    b = fx * dx + fy * dy
    c = fx * fx + fy * fy - r * r
    if c <= 0:
        return 0.0
    disc = b * b - c
    if disc < 0:
        return None
    t = -b - math.sqrt(disc)
    return t if t >= 0 else None
