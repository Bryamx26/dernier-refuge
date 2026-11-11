"""Schémas du contenu de jeu (`content/*.yaml`), validés strictement au démarrage du serveur.

Toute valeur de gameplay (armes, zombies, loot, survie) vit dans `content/` ; ce module ne fait que
la décrire et la valider. Un champ inconnu ou manquant empêche le démarrage.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ItemKind = Literal["melee", "firearm", "ammo", "food", "drink", "medical"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MeleeStats(_Strict):
    damage: float = Field(gt=0)
    range: float = Field(gt=0, le=3)
    arc_deg: float = Field(gt=0, le=360)
    cooldown_s: float = Field(gt=0)
    # Coups avant de casser ; 0 = incassable (poings).
    durability: int = Field(ge=0)
    noise: float = Field(ge=0)


class FirearmStats(_Strict):
    damage: float = Field(gt=0)
    pellets: int = Field(ge=1, le=16)
    range: float = Field(gt=0, le=40)
    spread_deg: float = Field(ge=0, le=90)
    cooldown_s: float = Field(gt=0)
    magazine: int = Field(ge=1)
    ammo: str
    reload_s: float = Field(gt=0)
    durability: int = Field(ge=1)
    noise: float = Field(ge=0)


class ConsumeEffect(_Strict):
    hunger: float = Field(default=0, ge=0, le=100)
    thirst: float = Field(default=0, ge=0, le=100)
    health: float = Field(default=0, ge=0, le=100)
    stops_bleeding: bool = False


class ItemDef(_Strict):
    name: str = Field(min_length=1, max_length=32)
    kind: ItemKind
    weight: float = Field(ge=0)
    stack: int = Field(ge=1, le=999)
    melee: MeleeStats | None = None
    firearm: FirearmStats | None = None
    consume: ConsumeEffect | None = None

    @model_validator(mode="after")
    def _check_kind(self) -> ItemDef:
        if (self.kind == "melee") != (self.melee is not None):
            raise ValueError("`melee` est requis pour kind=melee et interdit sinon")
        if (self.kind == "firearm") != (self.firearm is not None):
            raise ValueError("`firearm` est requis pour kind=firearm et interdit sinon")
        if (self.kind in ("food", "drink", "medical")) != (self.consume is not None):
            raise ValueError("`consume` est requis pour food/drink/medical et interdit sinon")
        if self.kind in ("melee", "firearm") and self.stack != 1:
            raise ValueError("une arme n'est pas empilable (stack: 1)")
        return self


class UnarmedDef(_Strict):
    name: str
    melee: MeleeStats


class ItemsFile(_Strict):
    unarmed: UnarmedDef
    items: dict[str, ItemDef]

    @model_validator(mode="after")
    def _check_refs(self) -> ItemsFile:
        for item_id, item in self.items.items():
            if item.firearm is not None:
                ammo = self.items.get(item.firearm.ammo)
                if ammo is None or ammo.kind != "ammo":
                    raise ValueError(f"{item_id} : munition `{item.firearm.ammo}` inconnue")
        return self


class ZombieType(_Strict):
    name: str = Field(min_length=1, max_length=24)
    health: float = Field(gt=0)
    half_size: float = Field(gt=0, lt=0.5)
    wander_speed: float = Field(ge=0)
    chase_speed: float = Field(gt=0)
    sight_range: float = Field(ge=0)
    sight_fov_deg: float = Field(gt=0, le=360)
    sense_range: float = Field(ge=0)
    hearing: float = Field(ge=0)
    attack_range: float = Field(gt=0)
    attack_damage: float = Field(ge=0)
    attack_cooldown_s: float = Field(gt=0)
    bleed_chance: float = Field(ge=0, le=1)
    wander_radius: float = Field(ge=0)
    leash_radius: float = Field(gt=0)
    search_s: float = Field(ge=0)


class PlayerNoise(_Strict):
    walk: float = Field(ge=0)
    sprint: float = Field(ge=0)


class ZombiesFile(_Strict):
    types: dict[str, ZombieType]
    player_noise: PlayerNoise


class LootEntry(_Strict):
    item: str
    weight: float = Field(gt=0)
    qty: tuple[int, int]


class LootTable(_Strict):
    rolls: tuple[int, int]
    empty_chance: float = Field(ge=0, le=1)
    entries: list[LootEntry] = Field(min_length=1)


class LootFile(_Strict):
    search_s: float = Field(ge=0)
    search_range: float = Field(gt=0)
    restock_s: float = Field(ge=0)
    buildings: dict[str, str]
    tables: dict[str, LootTable]

    @model_validator(mode="after")
    def _check_tables(self) -> LootFile:
        if "default" not in self.tables:
            raise ValueError("la table `default` est obligatoire")
        for building, table in self.buildings.items():
            if table not in self.tables:
                raise ValueError(f"bâtiment {building} : table `{table}` inconnue")
        for name, loot_table in self.tables.items():
            if not 0 <= loot_table.rolls[0] <= loot_table.rolls[1]:
                raise ValueError(f"table {name} : `rolls` doit être [min, max] avec 0 ≤ min ≤ max")
            for entry in loot_table.entries:
                if not 1 <= entry.qty[0] <= entry.qty[1]:
                    raise ValueError(f"table {name} : `qty` de {entry.item} invalide")
        return self


class StarterItem(_Strict):
    item: str
    qty: int = Field(ge=1)


class SurvivalConfig(_Strict):
    max_health: float = Field(gt=0)
    hunger_per_min: float = Field(ge=0)
    thirst_per_min: float = Field(ge=0)
    starving_damage_per_s: float = Field(ge=0)
    dehydrated_damage_per_s: float = Field(ge=0)
    bleeding_damage_per_s: float = Field(ge=0)
    regen_per_s: float = Field(ge=0)
    regen_threshold: float = Field(ge=0, le=100)
    inventory_slots: int = Field(ge=1, le=40)
    max_weight: float = Field(gt=0)
    starter_kit: list[StarterItem]


class ZombieGroup(_Strict):
    type: str
    count: int = Field(ge=0, le=200)
    x0: int
    x1: int
    y0: int
    y1: int


class ZonePopulation(_Strict):
    seed: int
    respawn_s: float = Field(ge=0)
    respawn_min_player_distance: float = Field(ge=0)
    zombie_groups: list[ZombieGroup]
