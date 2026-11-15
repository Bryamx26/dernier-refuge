"""Registre des zones en cours d'exécution dans ce processus."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path

from app.content.loader import CONTENT_DIR, load_content
from app.zone.movement import MOVEMENT_FILE, REPO_ROOT, MovementConfig
from app.zone.persistence import PlayerStore
from app.zone.runtime import ZoneRuntime
from app.zone.tilemap import ZoneMap, load_map

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ZoneSpec:
    """Paramètres d'une zone, issus de la table `zones` et de la configuration."""

    id: str
    name: str
    max_players: int
    tick_rate: int
    # Chemin de la carte relatif au dossier des données de jeu (`zones.map_file`, ex.
    # `maps/valcendre.tmj`). `None` : carte vide ouverte (tests unitaires).
    map_file: str | None = None


class ZoneManager:
    """Démarre une `ZoneRuntime` (et donc une boucle de tick) par zone.

    `data_dir` est la racine des données de jeu (`maps/`, `content/`, `shared/movement/movement.json`) ;
    par défaut la racine du dépôt. Si `allow_missing_maps` est vrai (environnement de test
    uniquement), une carte absente est remplacée par une carte vide ouverte de 128 × 128 tuiles ;
    sinon le démarrage échoue avec `MapLoadError`.
    """

    def __init__(
        self,
        *,
        store: PlayerStore | None = None,
        data_dir: Path | None = None,
        allow_missing_maps: bool = False,
    ) -> None:
        self.store = store
        self.data_dir = data_dir if data_dir is not None else REPO_ROOT
        self.allow_missing_maps = allow_missing_maps
        self._zones: dict[str, ZoneRuntime] = {}

    def _load_map(self, spec: ZoneSpec) -> ZoneMap:
        if spec.map_file is None:
            return ZoneMap.open_area(spec.id)
        path = self.data_dir / spec.map_file
        if not path.exists() and self.allow_missing_maps:
            logger.warning("zone %s : carte %s absente, carte vide de repli (test)", spec.id, path)
            return ZoneMap.open_area(path.stem)
        return load_map(path)

    async def start(self, specs: list[ZoneSpec]) -> None:
        """Charge toutes les cartes (échec immédiat si l'une manque) puis lance les zones."""
        movement = MovementConfig.load(self.data_dir / MOVEMENT_FILE)
        # Contenu de jeu : `content/` des données de jeu, à défaut celui du dépôt.
        content_dir = self.data_dir / CONTENT_DIR
        content = load_content(content_dir if content_dir.exists() else REPO_ROOT / CONTENT_DIR)
        runtimes: list[ZoneRuntime] = []
        for spec in specs:
            if spec.id in self._zones or any(r.spec.id == spec.id for r in runtimes):
                raise ValueError(f"zone {spec.id} déjà démarrée")
            zone_map = self._load_map(spec)
            runtimes.append(
                ZoneRuntime(
                    spec,
                    zone_map=zone_map,
                    movement=movement,
                    store=self.store,
                    content=content,
                    population=content.population(spec.id),
                )
            )
        for runtime in runtimes:
            runtime.start()
            self._zones[runtime.spec.id] = runtime

    async def stop(self) -> None:
        zones = list(self._zones.values())
        self._zones.clear()
        await asyncio.gather(*(zone.stop() for zone in zones))

    def get(self, zone_id: str) -> ZoneRuntime | None:
        return self._zones.get(zone_id)

    def online_count(self, zone_id: str) -> int:
        zone = self._zones.get(zone_id)
        return zone.online_count if zone is not None else 0
