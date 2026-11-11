"""Butin : bâtiments à fouiller (calque `buildings` de la carte, content/loot.yaml) et objets au sol."""

from __future__ import annotations

import random
from dataclasses import dataclass

from app.content.models import ItemDef, LootFile
from app.zone.inventory import ItemStack, new_stack


@dataclass(frozen=True, slots=True)
class BuildingInfo:
    """Bâtiment de la carte : nom et porte (tuile), lus dans le calque `buildings`."""

    name: str
    door_x: int
    door_y: int


@dataclass(slots=True)
class Building:
    info: BuildingInfo
    table: str
    # Tick à partir duquel le bâtiment peut être fouillé de nouveau.
    restocked_at: int = 0

    @property
    def door_center(self) -> tuple[float, float]:
        return (self.info.door_x + 0.5, self.info.door_y + 0.5)


@dataclass(slots=True)
class GroundItem:
    """Pile d'objets posée au sol, visible de tous (entité `item`)."""

    entity_id: str
    stack: ItemStack
    x: float
    y: float
    expires_at: int


def roll_loot(
    loot: LootFile, table_name: str, items: dict[str, ItemDef], rng: random.Random
) -> list[ItemStack]:
    """Tire le butin d'une table. Déterministe pour une graine donnée."""
    table = loot.tables.get(table_name) or loot.tables["default"]
    result: list[ItemStack] = []
    weights = [entry.weight for entry in table.entries]
    for _ in range(rng.randint(table.rolls[0], table.rolls[1])):
        if rng.random() < table.empty_chance:
            continue
        entry = rng.choices(table.entries, weights=weights)[0]
        qty = rng.randint(entry.qty[0], entry.qty[1])
        result.append(new_stack(entry.item, items[entry.item], qty))
    return result
