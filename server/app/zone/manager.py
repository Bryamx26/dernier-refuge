"""Registre des zones en cours d'exécution dans ce processus."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.zone.runtime import ZoneRuntime


@dataclass(frozen=True)
class ZoneSpec:
    """Paramètres d'une zone, issus de la table `zones` et de la configuration."""

    id: str
    name: str
    max_players: int
    tick_rate: int


class ZoneManager:
    """Démarre une `ZoneRuntime` (et donc une boucle de tick) par zone."""

    def __init__(self) -> None:
        self._zones: dict[str, ZoneRuntime] = {}

    async def start(self, specs: list[ZoneSpec]) -> None:
        for spec in specs:
            if spec.id in self._zones:
                raise ValueError(f"zone {spec.id} déjà démarrée")
            runtime = ZoneRuntime(spec)
            runtime.start()
            self._zones[spec.id] = runtime

    async def stop(self) -> None:
        zones = list(self._zones.values())
        self._zones.clear()
        await asyncio.gather(*(zone.stop() for zone in zones))

    def get(self, zone_id: str) -> ZoneRuntime | None:
        return self._zones.get(zone_id)

    def online_count(self, zone_id: str) -> int:
        zone = self._zones.get(zone_id)
        return zone.online_count if zone is not None else 0
