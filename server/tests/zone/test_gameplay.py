"""Règles de jeu de la phase 3 : contenu, inventaire, géométrie, zombies, combat, fouille, survie."""

from __future__ import annotations

import math
import random
from pathlib import Path

import pytest

from app.content.loader import ContentError, load_content
from app.content.models import ZombieGroup, ZonePopulation
from app.protocol.generated import ActionPayload, InputPayload
from app.zone.gameplay import Gameplay
from app.zone.geometry import DistanceField, line_of_sight, raycast
from app.zone.inventory import Inventory, ItemStack, new_stack
from app.zone.loot import BuildingInfo
from app.zone.movement import REPO_ROOT, CollisionGrid, MovementConfig
from app.zone.runtime import PlayerEntity
from app.zone.tilemap import ZoneMap
from app.zone.zombies import Zombie

CONTENT = load_content(REPO_ROOT / "content")
MOVEMENT = MovementConfig.load()
TICK_RATE = 20

# Carte de test 40 × 40 : bords solides, un mur vertical x = 20 (y 5..30), une porte de bâtiment en
# (10, 10) (tuile solide), point d'apparition en (5,5 ; 5,5).
ROWS = [
    "".join(
        "#" if x in (0, 39) or y in (0, 39) or (x == 20 and 5 <= y <= 30) or (x == 10 and y == 10) else "."
        for x in range(40)
    )
    for y in range(40)
]


def _map() -> ZoneMap:
    return ZoneMap(
        map_id="test",
        grid=CollisionGrid.from_rows(ROWS),
        spawns=[(5.5, 5.5)],
        buildings=[BuildingInfo(name="Pharmacie", door_x=10, door_y=10)],
    )


def _game(population: ZonePopulation | None = None, seed: int = 1) -> Gameplay:
    return Gameplay(
        CONTENT, _map(), MOVEMENT, tick_rate=TICK_RATE, population=population, rng=random.Random(seed)
    )


def _player(game: Gameplay, x: float, y: float, aim: float = 0.0, key: str = "c1") -> PlayerEntity:
    return PlayerEntity(
        entity_id=f"p-{key}", character_id=key, name=key, x=x, y=y, aim=aim, survivor=game.new_survivor()
    )


def _zombie(game: Gameplay, x: float, y: float, aim: float = math.pi) -> Zombie:
    kind = CONTENT.zombies.types["rodeur"]
    zombie = Zombie(
        entity_id=f"z{len(game.zombies) + 1}",
        type_id="rodeur",
        kind=kind,
        home=(x, y),
        x=x,
        y=y,
        health=kind.health,
        aim=aim,
    )
    zombie.timer = 60.0  # immobile (pause d'errance) tant qu'il ne perçoit rien
    game.zombies.append(zombie)
    return zombie


def _run(game: Gameplay, players: dict[str, PlayerEntity], seconds: float) -> None:
    for _ in range(round(seconds * TICK_RATE)):
        game.tick(players)


def _give(game: Gameplay, player: PlayerEntity, item_id: str, qty: int = 1) -> int:
    item = CONTENT.items.items[item_id]
    player.survivor.inventory.add(new_stack(item_id, item, qty))
    return next(i for i, s in player.survivor.inventory.slots.items() if s.item == item_id)


def _fire(game: Gameplay, player: PlayerEntity) -> None:
    game.on_input(player, InputPayload(move_x=0, move_y=0, aim=player.aim, sprint=False, attack=True), False)
    game.on_input(player, InputPayload(move_x=0, move_y=0, aim=player.aim, sprint=False, attack=False), False)


# --- Contenu -----------------------------------------------------------------------------------


def test_repository_content_is_valid() -> None:
    assert {"knife", "baseball_bat", "pistol", "shotgun"} <= CONTENT.items.items.keys()
    population = CONTENT.population("valcendre")
    assert population is not None and sum(g.count for g in population.zombie_groups) >= 30


def test_invalid_content_is_rejected(tmp_path: Path) -> None:
    for name in ("items.yaml", "zombies.yaml", "loot.yaml", "survival.yaml"):
        (tmp_path / name).write_text(
            (REPO_ROOT / "content" / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    loot = tmp_path / "loot.yaml"
    loot.write_text(
        loot.read_text(encoding="utf-8").replace("item: bandage", "item: laser"), encoding="utf-8"
    )
    with pytest.raises(ContentError, match="laser"):
        load_content(tmp_path)


# --- Inventaire --------------------------------------------------------------------------------


def _inventory(capacity: int = 4, max_weight: float = 10.0) -> Inventory:
    return Inventory(CONTENT.items.items, capacity, max_weight)


def test_inventory_stacks_slots_and_weight() -> None:
    inv = _inventory(capacity=3, max_weight=5.0)
    bandage = CONTENT.items.items["bandage"]
    assert inv.add(new_stack("bandage", bandage, 15)) == 0  # pile de 10 + pile de 5
    assert sorted(s.qty for s in inv.slots.values()) == [5, 10]
    shotgun = CONTENT.items.items["shotgun"]
    assert inv.add(new_stack("shotgun", shotgun, 1)) == 0
    # Plus d'emplacement libre : les bandages complètent la pile existante, le reste est refusé.
    assert inv.add(new_stack("bandage", bandage, 8)) == 3
    # Poids : 5 kg max, déjà 3,2 + 0,75 ; une batte (1 kg) passe, une seconde non.
    inv2 = _inventory(capacity=5, max_weight=1.5)
    bat = CONTENT.items.items["baseball_bat"]
    assert inv2.add(new_stack("baseball_bat", bat, 1)) == 0
    assert inv2.add(new_stack("baseball_bat", bat, 1)) == 1


def test_inventory_json_round_trip_and_payload() -> None:
    inv = _inventory()
    inv.add(ItemStack("pistol", 1, durability=200, loaded=7))
    inv.add(new_stack("ammo_9mm", CONTENT.items.items["ammo_9mm"], 30))
    inv.equipped = 0
    copy = _inventory()
    copy.load_json(inv.to_json())
    assert copy.to_json() == inv.to_json()
    payload = copy.payload()
    pistol = payload.slots[0]
    assert (pistol.item, pistol.loaded, pistol.durability, payload.equipped) == ("pistol", 7, 0.5, 0)
    # Entrées corrompues ou objets disparus : ignorés.
    copy.load_json({"slots": [{"slot": 0, "item": "laser", "qty": 1}, {"slot": "x"}], "equipped": 3})
    assert copy.slots == {} and copy.equipped == -1


# --- Géométrie ---------------------------------------------------------------------------------


def test_raycast_and_line_of_sight() -> None:
    grid = CollisionGrid.from_rows(ROWS)
    assert raycast(grid, 15.5, 10.5, 1.0, 0.0, 30) == pytest.approx(4.5)
    assert raycast(grid, 15.5, 10.5, 0.0, 1.0, 5) == 5
    assert not line_of_sight(grid, 15.5, 10.5, 25.5, 10.5)
    assert line_of_sight(grid, 15.5, 35.5, 25.5, 35.5)


def test_distance_field_goes_around_wall() -> None:
    grid = CollisionGrid.from_rows(ROWS)
    field = DistanceField(grid, 25, 10, radius=30)
    # De l'autre côté du mur, le chemin le contourne par le haut (y < 5) : 22 pas au lieu de 10.
    assert field.distance(15, 10) == 22
    nxt = field.next_tile(15, 10)
    assert nxt is not None and field.distance(*nxt) == field.distance(15, 10) - 1


# --- Zombies -----------------------------------------------------------------------------------


def test_zombie_sees_player_in_front_but_not_behind_wall() -> None:
    game = _game()
    players = {"c1": _player(game, 25.5, 12.0)}
    behind_wall = _zombie(game, 15.5, 12.0, aim=0.0)
    in_view = _zombie(game, 30.5, 12.0, aim=math.pi)
    _run(game, players, 0.3)
    assert in_view.state == "chase" and in_view.target == "c1"
    assert behind_wall.state == "wander"


def test_zombie_does_not_see_behind_its_back_but_hears_gunshot() -> None:
    game = _game()
    player = _player(game, 25.5, 12.0, aim=0.0)
    players = {"c1": player}
    zombie = _zombie(game, 31.5, 12.0, aim=0.0)  # dos tourné au joueur, à 6 tuiles
    _run(game, players, 0.5)
    assert zombie.state == "wander"
    slot = _give(game, player, "pistol")
    player.survivor.inventory.equipped = slot
    player.survivor.inventory.slots[slot].loaded = 3
    player.aim = math.pi / 2  # tir vers le bas : le bruit suffit
    _fire(game, player)
    _run(game, players, 0.1)
    assert zombie.state in ("investigate", "chase")
    _run(game, players, 2.0)
    assert zombie.state == "chase"


def test_zombie_chases_around_wall_and_attacks() -> None:
    game = _game()
    player = _player(game, 22.5, 34.0)
    players = {"c1": player}
    zombie = _zombie(game, 17.5, 34.0, aim=0.0)
    _run(game, players, 0.3)
    assert zombie.state == "chase"
    # Le joueur passe derrière le mur : le zombie le contourne grâce au champ de distances.
    player.x, player.y = 22.5, 20.0
    _run(game, players, 12.0)
    assert zombie.state == "chase"
    assert math.hypot(zombie.x - player.x, zombie.y - player.y) <= zombie.kind.attack_range + 0.05
    assert player.survivor.vitals.health < CONTENT.survival.max_health


def test_zombie_kills_player_who_drops_inventory_then_respawns() -> None:
    game = _game()
    player = _player(game, 25.5, 12.0)
    players = {"c1": player}
    _zombie(game, 26.3, 12.0)
    _run(game, players, 30.0)
    s = player.survivor
    assert s.vitals.dead and player.anim == "dead"
    assert not s.inventory.slots and game.ground, "équipement lâché au sol"
    game.on_action(player, ActionPayload(kind="respawn", slot=-1))
    assert not s.vitals.dead and s.inventory.slots
    assert (player.x, player.y) == (5.5, 5.5)


def test_zombie_gives_up_beyond_leash_and_returns_home() -> None:
    game = _game()
    zombie = _zombie(game, 30.5, 34.0)
    zombie.x = 30.5 - zombie.kind.leash_radius - 1  # trop loin de chez lui
    player = _player(game, zombie.x - 3, 34.0)
    zombie.aim = math.pi
    _run(game, {"c1": player}, 0.3)
    assert zombie.state in ("return", "wander")


def test_population_places_zombies_on_free_tiles_away_from_spawn() -> None:
    population = ZonePopulation(
        seed=3,
        respawn_s=1,
        respawn_min_player_distance=0,
        spawn_safe_radius=8,
        zombie_groups=[ZombieGroup(type="rodeur", count=12, x0=1, x1=38, y0=1, y1=38)],
    )
    game = _game(population)
    grid = CollisionGrid.from_rows(ROWS)
    assert len(game.zombies) == 12
    for z in game.zombies:
        assert not grid.is_solid(math.floor(z.x), math.floor(z.y))
        assert math.hypot(z.x - 5.5, z.y - 5.5) > 8
    # Même graine, même placement.
    assert [(z.x, z.y) for z in _game(population, seed=99).zombies] == [(z.x, z.y) for z in game.zombies]


# --- Combat ------------------------------------------------------------------------------------


def test_pistol_kills_zombie_in_line_but_wall_stops_bullets() -> None:
    game = _game()
    player = _player(game, 15.5, 12.5, aim=0.0)
    players = {"c1": player}
    slot = _give(game, player, "pistol")
    player.survivor.inventory.equipped = slot
    player.survivor.inventory.slots[slot].loaded = 12
    shielded = _zombie(game, 23.5, 12.5)  # derrière le mur x = 20
    target = _zombie(game, 15.5, 18.5)
    for _ in range(4):
        _fire(game, player)
        _run(game, players, 0.4)
    assert shielded.health == shielded.kind.health
    player.aim = math.pi / 2
    shots = 0
    while target.alive and shots < 6:
        _fire(game, player)
        _run(game, players, 0.4)
        shots += 1
    assert not target.alive
    assert any(f.event.kind == "shot" for f in game.fx) or shots > 0
    assert player.survivor.inventory.slots[slot].loaded == 12 - 4 - shots


def test_empty_magazine_reload_consumes_ammo() -> None:
    game = _game()
    player = _player(game, 15.5, 12.5)
    players = {"c1": player}
    slot = _give(game, player, "pistol")
    _give(game, player, "ammo_9mm", 20)
    game.on_action(player, ActionPayload(kind="use", slot=slot))
    assert player.survivor.inventory.equipped == slot
    _fire(game, player)
    assert any("Chargeur vide" in n for n in player.survivor.notices)
    game.on_action(player, ActionPayload(kind="reload", slot=-1))
    assert player.survivor.action is not None
    _run(game, players, 2.0)
    s = player.survivor
    assert s.inventory.slots[slot].loaded == 12 and s.inventory.count("ammo_9mm") == 8


def test_melee_hits_in_arc_only_and_weapon_breaks() -> None:
    game = _game()
    player = _player(game, 15.5, 12.5, aim=0.0)
    players = {"c1": player}
    slot = _give(game, player, "knife")
    player.survivor.inventory.equipped = slot
    player.survivor.inventory.slots[slot].durability = 2
    behind = _zombie(game, 14.6, 12.5)
    front = _zombie(game, 16.4, 12.5)
    _fire(game, player)
    assert front.health < front.kind.health and behind.health == behind.kind.health
    _run(game, players, 1.0)
    player.aim = 0.0
    front.x, front.y = 16.4, 12.5
    _fire(game, player)
    assert slot not in player.survivor.inventory.slots and player.survivor.inventory.equipped == -1


# --- Fouille et objets ---------------------------------------------------------------------------


def test_search_building_gives_loot_once_then_restocks_later() -> None:
    game = _game(seed=5)
    player = _player(game, 10.5, 11.4)
    players = {"c1": player}
    before = sum(s.qty for s in player.survivor.inventory.slots.values())
    game.on_action(player, ActionPayload(kind="interact", slot=-1))
    assert player.survivor.action is not None and player.survivor.action.kind == "search"
    _run(game, players, CONTENT.loot.search_s + 0.1)
    assert player.survivor.action is None
    after = sum(s.qty for s in player.survivor.inventory.slots.values()) + sum(
        g.stack.qty for g in game.ground.values()
    )
    notices = " ".join(player.survivor.notices)
    assert after > before or "rien trouvé" in notices
    player.survivor.notices.clear()
    game.on_action(player, ActionPayload(kind="interact", slot=-1))
    assert player.survivor.action is None and "déjà fouillé" in player.survivor.notices[0]


def test_moving_cancels_search() -> None:
    game = _game()
    player = _player(game, 10.5, 11.4)
    game.on_action(player, ActionPayload(kind="interact", slot=-1))
    game.on_input(player, InputPayload(move_x=1, move_y=0, aim=0, sprint=False, attack=False), True)
    assert player.survivor.action is None


def test_drop_and_pick_up() -> None:
    game = _game()
    player = _player(game, 25.5, 25.5)
    slot = _give(game, player, "baseball_bat")
    game.on_action(player, ActionPayload(kind="drop", slot=slot))
    assert slot not in player.survivor.inventory.slots and len(game.ground) == 1
    states = [e for _, _, e in game.world_entities() if e.kind == "item"]
    assert states[0].name == "Batte de baseball"
    game.on_action(player, ActionPayload(kind="interact", slot=-1))
    assert player.survivor.inventory.count("baseball_bat") == 1 and not game.ground


# --- Survie ------------------------------------------------------------------------------------


def test_hunger_thirst_starvation_and_bandage() -> None:
    game = _game()
    player = _player(game, 25.5, 25.5)
    players = {"c1": player}
    v = player.survivor.vitals
    _run(game, players, 60.0)
    assert v.hunger == pytest.approx(100 - CONTENT.survival.hunger_per_min, abs=0.01)
    assert v.thirst == pytest.approx(100 - CONTENT.survival.thirst_per_min, abs=0.01)
    v.thirst = 0.0
    v.bleeding = True
    health = v.health
    _run(game, players, 2.0)
    expected = 2.0 * (CONTENT.survival.dehydrated_damage_per_s + CONTENT.survival.bleeding_damage_per_s)
    assert health - v.health == pytest.approx(expected, abs=0.05)
    bandage = _give(game, player, "bandage")
    water = _give(game, player, "water_bottle")
    game.on_action(player, ActionPayload(kind="use", slot=bandage))
    game.on_action(player, ActionPayload(kind="use", slot=water))
    assert not v.bleeding and v.thirst == 40


def test_real_zone_tick_cost_with_zombies() -> None:
    """Valcendre peuplée, 8 joueurs dispersés dans le village : un tick reste bien sous 50 ms."""
    import time

    from app.zone.tilemap import load_map

    zone_map = load_map(REPO_ROOT / "maps" / "valcendre.tmj")
    game = Gameplay(
        CONTENT,
        zone_map,
        MOVEMENT,
        tick_rate=TICK_RATE,
        population=CONTENT.population("valcendre"),
        rng=random.Random(2),
    )
    assert len(game.zombies) >= 30
    spots = [
        (60.5, 62.5),
        (100.5, 63.5),
        (40.5, 63.5),
        (85.5, 92.5),
        (25.5, 100.5),
        (70.5, 20.5),
        (71.5, 110.5),
        (88.5, 75.5),
    ]
    players = {f"c{i}": _player(game, x, y, key=f"c{i}") for i, (x, y) in enumerate(spots)}
    started = time.perf_counter()
    _run(game, players, 10.0)
    mean_ms = (time.perf_counter() - started) * 1000 / (10 * TICK_RATE)
    assert sum(z.state == "chase" for z in game.zombies) > 0
    assert mean_ms < 10, f"{mean_ms:.2f} ms par tick"


def test_zombie_returns_home_around_wall() -> None:
    """Un zombie qui rentre contourne le mur au lieu de rester bloqué (et de s'installer ailleurs)."""
    game = _game()
    zombie = _zombie(game, 25.5, 12.5)
    zombie.x, zombie.y = 15.5, 12.5  # de l'autre côté du mur x = 20
    zombie.state, zombie.goal = "return", zombie.home
    _run(game, {}, 25.0)
    assert zombie.home == (25.5, 12.5)
    assert math.hypot(zombie.x - 25.5, zombie.y - 12.5) < 6
