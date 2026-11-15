"""Inventaire d'un personnage : emplacements, piles, poids, usure et chargeurs.

Les définitions d'objets viennent de `content/items.yaml`. L'inventaire est sérialisé en JSON pour
la base (`characters.inventory`) et converti en message `inventory` pour le client.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.content.models import ItemDef
from app.protocol.generated import InventoryPayload, InventorySlot


@dataclass(slots=True)
class ItemStack:
    """Une pile d'objets identiques. `durability` : utilisations restantes (armes), `loaded` : chargeur."""

    item: str
    qty: int
    durability: int = 0
    loaded: int = 0


def new_stack(item_id: str, item: ItemDef, qty: int) -> ItemStack:
    """Pile neuve : armes à pleine usure et chargeur vide."""
    durability = 0
    if item.melee is not None:
        durability = item.melee.durability
    elif item.firearm is not None:
        durability = item.firearm.durability
    return ItemStack(item=item_id, qty=qty, durability=durability)


class Inventory:
    """`capacity` emplacements indexés ; `equipped` : emplacement de l'arme en main (-1 : aucune)."""

    def __init__(self, items: dict[str, ItemDef], capacity: int, max_weight: float) -> None:
        self.defs = items
        self.capacity = capacity
        self.max_weight = max_weight
        self.slots: dict[int, ItemStack] = {}
        self.equipped = -1

    # --- Lecture ---------------------------------------------------------------------------------

    def weight(self) -> float:
        return sum(self.defs[s.item].weight * s.qty for s in self.slots.values() if s.item in self.defs)

    def count(self, item_id: str) -> int:
        return sum(s.qty for s in self.slots.values() if s.item == item_id)

    def equipped_stack(self) -> ItemStack | None:
        return self.slots.get(self.equipped)

    def _free_slot(self) -> int | None:
        for index in range(self.capacity):
            if index not in self.slots:
                return index
        return None

    # --- Écriture --------------------------------------------------------------------------------

    def add(self, stack: ItemStack) -> int:
        """Range `stack` (complète d'abord les piles existantes). Renvoie la quantité qui ne rentre
        pas (emplacements ou poids). `stack` n'est pas modifiée."""
        item = self.defs.get(stack.item)
        if item is None:
            return stack.qty
        remaining = stack.qty
        if item.weight > 0:
            room = int((self.max_weight - self.weight()) / item.weight + 1e-9)
            remaining = min(remaining, max(0, room))
        refused = stack.qty - remaining
        if item.stack > 1:
            for existing in self.slots.values():
                if remaining == 0:
                    break
                if existing.item == stack.item and existing.qty < item.stack:
                    moved = min(item.stack - existing.qty, remaining)
                    existing.qty += moved
                    remaining -= moved
        while remaining > 0:
            index = self._free_slot()
            if index is None:
                break
            moved = min(item.stack, remaining)
            self.slots[index] = ItemStack(stack.item, moved, stack.durability, stack.loaded)
            remaining -= moved
        return refused + remaining

    def take(self, slot: int, qty: int = 1) -> ItemStack | None:
        """Retire `qty` objets de l'emplacement (toute la pile si `qty` la dépasse)."""
        stack = self.slots.get(slot)
        if stack is None or qty <= 0:
            return None
        if qty >= stack.qty:
            del self.slots[slot]
            if self.equipped == slot:
                self.equipped = -1
            return stack
        stack.qty -= qty
        return ItemStack(stack.item, qty, stack.durability, stack.loaded)

    def consume(self, item_id: str, qty: int) -> int:
        """Retire jusqu'à `qty` objets `item_id`, en commençant par les plus petites piles."""
        taken = 0
        for index, stack in sorted(
            ((i, s) for i, s in self.slots.items() if s.item == item_id), key=lambda pair: pair[1].qty
        ):
            if taken >= qty:
                break
            part = min(stack.qty, qty - taken)
            self.take(index, part)
            taken += part
        return taken

    def clear(self) -> list[ItemStack]:
        stacks = list(self.slots.values())
        self.slots.clear()
        self.equipped = -1
        return stacks

    # --- Sérialisation -----------------------------------------------------------------------------

    def to_json(self) -> dict[str, Any]:
        return {
            "equipped": self.equipped,
            "slots": [
                {"slot": i, "item": s.item, "qty": s.qty, "durability": s.durability, "loaded": s.loaded}
                for i, s in sorted(self.slots.items())
            ],
        }

    def load_json(self, data: Any) -> None:
        """Recharge un inventaire sauvegardé ; ignore les entrées invalides ou les objets disparus."""
        self.clear()
        if not isinstance(data, dict):
            return
        for raw in data.get("slots", []):
            try:
                slot, item_id, qty = int(raw["slot"]), str(raw["item"]), int(raw["qty"])
                durability, loaded = int(raw.get("durability", 0)), int(raw.get("loaded", 0))
            except (KeyError, TypeError, ValueError):
                continue
            item = self.defs.get(item_id)
            if item is None or not 0 <= slot < self.capacity or slot in self.slots or qty < 1:
                continue
            self.slots[slot] = ItemStack(item_id, min(qty, item.stack), max(0, durability), max(0, loaded))
        equipped = data.get("equipped", -1)
        if isinstance(equipped, int) and equipped in self.slots:
            self.equipped = equipped

    def payload(self) -> InventoryPayload:
        slots: list[InventorySlot] = []
        for index, stack in sorted(self.slots.items()):
            item = self.defs[stack.item]
            full = item.melee.durability if item.melee else item.firearm.durability if item.firearm else 0
            slots.append(
                InventorySlot(
                    slot=index,
                    item=stack.item,
                    name=item.name,
                    kind=item.kind,
                    qty=stack.qty,
                    weight=round(item.weight * stack.qty, 3),
                    durability=min(1.0, stack.durability / full) if full > 0 else 1.0,
                    loaded=stack.loaded,
                )
            )
        return InventoryPayload(
            slots=slots,
            capacity=self.capacity,
            equipped=self.equipped,
            weight=round(self.weight(), 3),
            max_weight=self.max_weight,
        )
