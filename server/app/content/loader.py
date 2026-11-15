"""Chargement et validation croisée du contenu de jeu (`content/`)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from app.content.models import (
    ItemDef,
    ItemsFile,
    LootFile,
    SurvivalConfig,
    ZombiesFile,
    ZonePopulation,
)

CONTENT_DIR = Path("content")


class ContentError(Exception):
    """Fichier de contenu absent, illisible ou invalide."""


def _read[M: BaseModel](path: Path, model: type[M]) -> M:
    try:
        with path.open(encoding="utf-8") as handle:
            data: Any = yaml.safe_load(handle)
    except FileNotFoundError:
        raise ContentError(f"contenu introuvable : {path}") from None
    except (OSError, yaml.YAMLError) as exc:
        raise ContentError(f"contenu illisible ({path}) : {exc}") from exc
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ContentError(f"contenu invalide ({path}) :\n{exc}") from exc


@dataclass(frozen=True)
class GameContent:
    """Tout le contenu global (hors peuplement des zones)."""

    items: ItemsFile
    zombies: ZombiesFile
    loot: LootFile
    survival: SurvivalConfig
    # Peuplement par zone (`content/zones/<zone_id>.yaml`), chargé à la demande.
    root: Path = field(default=Path())

    def item(self, item_id: str) -> ItemDef | None:
        return self.items.items.get(item_id)

    def population(self, zone_id: str) -> ZonePopulation | None:
        """Peuplement de la zone, ou None si elle n'a pas de fichier (zone sans zombies)."""
        path = self.root / "zones" / f"{zone_id}.yaml"
        if not path.exists():
            return None
        population = _read(path, ZonePopulation)
        for group in population.zombie_groups:
            if group.type not in self.zombies.types:
                raise ContentError(f"{path} : type de zombie `{group.type}` inconnu")
            if group.x0 > group.x1 or group.y0 > group.y1:
                raise ContentError(f"{path} : rectangle de groupe invalide")
        return population


def load_content(root: Path) -> GameContent:
    """Lit `root` (dossier `content/`) et vérifie les références entre fichiers."""
    items = _read(root / "items.yaml", ItemsFile)
    zombies = _read(root / "zombies.yaml", ZombiesFile)
    loot = _read(root / "loot.yaml", LootFile)
    survival = _read(root / "survival.yaml", SurvivalConfig)
    known = items.items
    for name, table in loot.tables.items():
        for entry in table.entries:
            item = known.get(entry.item)
            if item is None:
                raise ContentError(f"loot.yaml, table {name} : objet `{entry.item}` inconnu")
            if entry.qty[1] > item.stack:
                raise ContentError(f"loot.yaml, table {name} : `{entry.item}` dépasse sa pile ({item.stack})")
    for starter in survival.starter_kit:
        if starter.item not in known:
            raise ContentError(f"survival.yaml : objet de départ `{starter.item}` inconnu")
    return GameContent(items=items, zombies=zombies, loot=loot, survival=survival, root=root)
