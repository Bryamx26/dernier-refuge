"""AUTO-GÉNÉRÉ par tools/codegen/generate.py depuis shared/protocol/protocol.json. Ne pas modifier."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PROTOCOL_VERSION = 3


class ProtocolModel(BaseModel):
    """Base des charges utiles : champs inconnus refusés, instances immuables."""

    model_config = ConfigDict(extra="forbid", frozen=True)


ErrorCode = Literal["bad_message", "unknown_type", "rate_limited", "internal"]


AnimState = Literal["idle", "walk", "run", "attack", "dead"]


EntityKind = Literal["player", "zombie", "item"]


class EntityState(ProtocolModel):
    """État d'une entité visible dans un snapshot. Positions en tuiles, angle en radians."""

    id: str = Field(min_length=1, max_length=64)
    kind: EntityKind
    name: str = Field(max_length=32, description="Nom du joueur, type de zombie ou nom de l'objet au sol.")
    x: float
    y: float
    aim: float = Field(description="Orientation en radians (0 = vers la droite, sens horaire écran).")
    anim: AnimState
    health: float = Field(ge=0, le=1, description="Santé relative, de 0 (mort) à 1.")


ItemKind = Literal["melee", "firearm", "ammo", "food", "drink", "medical"]


class InventorySlot(ProtocolModel):
    """Un emplacement occupé de l'inventaire."""

    slot: int = Field(ge=0, le=63, description="Index de l'emplacement.")
    item: str = Field(min_length=1, max_length=32, description="Identifiant de l'objet (content/items.yaml).")
    name: str = Field(max_length=32)
    kind: ItemKind
    qty: int = Field(ge=1)
    weight: float = Field(ge=0, description="Poids de la pile, en kg.")
    durability: float = Field(ge=0, le=1, description="Usure restante de 0 à 1 (1 pour un objet sans usure).")
    loaded: int = Field(ge=0, description="Munitions dans le chargeur (armes à feu, 0 sinon).")


FxKind = Literal["shot", "swing", "hit", "blood", "search"]


class FxEvent(ProtocolModel):
    """Effet visuel : de (x, y) vers (x2, y2) pour un tir, au point (x, y) sinon."""

    kind: FxKind
    x: float
    y: float
    x2: float
    y2: float


ActionKind = Literal["interact", "use", "drop", "reload", "respawn"]


class PingPayload(ProtocolModel):
    """Mesure de latence, envoyé environ une fois par seconde."""

    client_time: float = Field(ge=0, description="Horodatage client en millisecondes (performance.now()).")


class InputPayload(ProtocolModel):
    """Entrée pour UN pas de simulation (1/tick_rate s). Envoyé à tick_rate Hz. Le `seq` de l'enveloppe sert de numéro d'entrée pour la réconciliation."""

    move_x: float = Field(ge=-1, le=1, description="Axe horizontal, -1 (gauche) à 1 (droite).")
    move_y: float = Field(ge=-1, le=1, description="Axe vertical, -1 (haut) à 1 (bas).")
    aim: float = Field(ge=-7, le=7, description="Orientation souhaitée en radians.")
    sprint: bool
    attack: bool = Field(description="Gâchette (clic gauche) tenue pendant ce pas.")


class ActionPayload(ProtocolModel):
    """Action ponctuelle, traitée au tick suivant : fouiller/ramasser (interact), utiliser ou équiper l'emplacement `slot` (use), le jeter (drop), recharger (reload), réapparaître après la mort (respawn)."""

    kind: ActionKind
    slot: int = Field(ge=-1, le=63, description="Emplacement visé (use, drop), -1 sinon.")


class WelcomePayload(ProtocolModel):
    """Premier message après l'ouverture du WebSocket."""

    protocol_version: int = Field(ge=1)
    zone_id: str = Field(min_length=1, max_length=64)
    character_id: str = Field(min_length=1, max_length=64)
    tick_rate: int = Field(ge=1, description="Ticks de simulation par seconde.")
    server_time: float = Field(ge=0, description="Horodatage serveur en millisecondes.")
    entity_id: str = Field(min_length=1, max_length=64, description="Identifiant de l'entité du joueur dans les snapshots.")
    map_id: str = Field(min_length=1, max_length=64, description="Carte de la zone, chargée depuis /game/maps/<map_id>.tmj.")


class SnapshotPayload(ProtocolModel):
    """État des entités proches du joueur, envoyé à chaque tick. Une entité absente du snapshot n'est plus visible."""

    ack_seq: int = Field(ge=0, description="`seq` de la dernière entrée du joueur appliquée par le serveur (0 si aucune).")
    entities: list[EntityState]


class PongPayload(ProtocolModel):
    """Réponse à `ping`."""

    client_time: float = Field(ge=0)
    server_time: float = Field(ge=0)


class VitalsPayload(ProtocolModel):
    """État du personnage, envoyé à chaque changement et au moins deux fois par seconde."""

    health: float = Field(ge=0)
    max_health: float = Field(ge=0)
    hunger: float = Field(ge=0, le=100, description="0 (affamé) à 100 (rassasié).")
    thirst: float = Field(ge=0, le=100, description="0 (assoiffé) à 100 (désaltéré).")
    bleeding: bool
    dead: bool
    action: str = Field(max_length=48, description="Action longue en cours (« Fouille : Pharmacie », « Rechargement »), vide sinon.")
    action_progress: float = Field(ge=0, le=1, description="Avancement de l'action longue, de 0 à 1.")


class InventoryPayload(ProtocolModel):
    """Inventaire complet du joueur, envoyé à chaque changement."""

    slots: list[InventorySlot] = Field(max_length=64)
    capacity: int = Field(ge=1, description="Nombre d'emplacements.")
    equipped: int = Field(ge=-1, description="Emplacement de l'arme en main, -1 : mains nues.")
    weight: float = Field(ge=0)
    max_weight: float = Field(ge=0)


class FxPayload(ProtocolModel):
    """Effets visuels du tick, autour du joueur."""

    events: list[FxEvent] = Field(max_length=128)


class NoticePayload(ProtocolModel):
    """Message court affiché au joueur (butin, inventaire plein…)."""

    text: str = Field(min_length=1, max_length=120)


class ErrorPayload(ProtocolModel):
    """Message refusé ou erreur interne. La connexion reste ouverte sauf mention contraire."""

    code: ErrorCode
    message: str = Field(max_length=200)


ClientMessageType = Literal["ping", "input", "action"]
CLIENT_MESSAGES: dict[str, type[ProtocolModel]] = {"ping": PingPayload, "input": InputPayload, "action": ActionPayload}

ServerMessageType = Literal["welcome", "snapshot", "pong", "vitals", "inventory", "fx", "notice", "error"]
SERVER_MESSAGES: dict[str, type[ProtocolModel]] = {"welcome": WelcomePayload, "snapshot": SnapshotPayload, "pong": PongPayload, "vitals": VitalsPayload, "inventory": InventoryPayload, "fx": FxPayload, "notice": NoticePayload, "error": ErrorPayload}
