"""Jauges de survie d'un personnage : santé, faim, soif, saignement (content/survival.yaml)."""

from __future__ import annotations

from dataclasses import dataclass

from app.content.models import ConsumeEffect, SurvivalConfig


@dataclass(slots=True)
class Vitals:
    health: float
    hunger: float = 100.0
    thirst: float = 100.0
    bleeding: bool = False

    @property
    def dead(self) -> bool:
        return self.health <= 0

    @classmethod
    def fresh(cls, config: SurvivalConfig) -> Vitals:
        return cls(health=config.max_health)

    def tick(self, config: SurvivalConfig, dt: float) -> None:
        """Avance les jauges de `dt` secondes (sans effet sur un mort)."""
        if self.dead:
            return
        self.hunger = max(0.0, self.hunger - config.hunger_per_min * dt / 60)
        self.thirst = max(0.0, self.thirst - config.thirst_per_min * dt / 60)
        damage = 0.0
        if self.hunger <= 0:
            damage += config.starving_damage_per_s * dt
        if self.thirst <= 0:
            damage += config.dehydrated_damage_per_s * dt
        if self.bleeding:
            damage += config.bleeding_damage_per_s * dt
        if damage > 0:
            self.health = max(0.0, self.health - damage)
        elif self.hunger >= config.regen_threshold and self.thirst >= config.regen_threshold:
            self.health = min(config.max_health, self.health + config.regen_per_s * dt)

    def hurt(self, amount: float) -> None:
        self.health = max(0.0, self.health - amount)

    def apply(self, effect: ConsumeEffect, config: SurvivalConfig) -> None:
        """Effet d'un consommable (nourriture, boisson, soin)."""
        self.hunger = min(100.0, self.hunger + effect.hunger)
        self.thirst = min(100.0, self.thirst + effect.thirst)
        self.health = min(config.max_health, self.health + effect.health)
        if effect.stops_bleeding:
            self.bleeding = False
