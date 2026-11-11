"""Génère les types du protocole WebSocket depuis shared/protocol/protocol.json.

Sorties :
  - server/app/protocol/generated.py  (modèles Pydantic)
  - client/src/generated/protocol.ts  (types TypeScript)

Usage :
  python tools/codegen/generate.py          # écrit les fichiers
  python tools/codegen/generate.py --check  # échoue si les fichiers ne sont pas à jour (CI)

Le sous-ensemble de JSON Schema accepté est volontairement réduit : objets à
propriétés nommées, string (avec enum), integer, number, boolean, array et
$ref vers `#/defs/<Nom>`. Tout autre mot-clé fait échouer la génération, pour
qu'aucun contrat ne soit ignoré silencieusement.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "shared" / "protocol" / "protocol.json"
PY_OUT = ROOT / "server" / "app" / "protocol" / "generated.py"
TS_OUT = ROOT / "client" / "src" / "generated" / "protocol.ts"

HEADER = "AUTO-GÉNÉRÉ par tools/codegen/generate.py depuis shared/protocol/protocol.json. Ne pas modifier."

ALLOWED_KEYS = {
    "description",
    "type",
    "enum",
    "properties",
    "required",
    "items",
    "$ref",
    "minimum",
    "maximum",
    "minLength",
    "maxLength",
    "maxItems",
}
CONSTRAINTS_PY = {
    "minimum": "ge",
    "maximum": "le",
    "minLength": "min_length",
    "maxLength": "max_length",
    "maxItems": "max_length",
}


class SchemaError(Exception):
    pass


def pascal(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


def check_keys(schema: dict[str, Any], where: str) -> None:
    unknown = set(schema) - ALLOWED_KEYS
    if unknown:
        raise SchemaError(f"{where}: mots-clés non pris en charge {sorted(unknown)}")


def ref_name(ref: str, defs: dict[str, Any], where: str) -> str:
    prefix = "#/defs/"
    if not ref.startswith(prefix) or ref[len(prefix) :] not in defs:
        raise SchemaError(f"{where}: référence inconnue {ref}")
    return ref[len(prefix) :]


# --------------------------------------------------------------------------- Python


def py_type(schema: dict[str, Any], defs: dict[str, Any], where: str) -> str:
    check_keys(schema, where)
    if "$ref" in schema:
        return ref_name(schema["$ref"], defs, where)
    kind = schema.get("type")
    if kind == "string":
        if "enum" in schema:
            return "Literal[" + ", ".join(json.dumps(v) for v in schema["enum"]) + "]"
        return "str"
    if kind == "integer":
        return "int"
    if kind == "number":
        return "float"
    if kind == "boolean":
        return "bool"
    if kind == "array":
        return f"list[{py_type(schema['items'], defs, where + '[]')}]"
    raise SchemaError(f"{where}: type non pris en charge {kind!r}")


def py_field(schema: dict[str, Any], required: bool) -> str:
    args = [f"{CONSTRAINTS_PY[k]}={schema[k]!r}" for k in CONSTRAINTS_PY if k in schema]
    if "description" in schema:
        args.append(f"description={json.dumps(schema['description'], ensure_ascii=False)}")
    if not required:
        args.insert(0, "default=None")
    return f" = Field({', '.join(args)})" if args else ""


def py_object(name: str, schema: dict[str, Any], defs: dict[str, Any]) -> list[str]:
    check_keys(schema, name)
    if schema.get("type") != "object":
        raise SchemaError(f"{name}: doit être un objet")
    lines = [f"class {name}(ProtocolModel):"]
    if "description" in schema:
        lines.append(f'    """{schema["description"]}"""')
        lines.append("")
    required = set(schema.get("required", []))
    props = schema.get("properties", {})
    if not props:
        lines.append("    pass")
    for prop, sub in props.items():
        annotation = py_type(sub, defs, f"{name}.{prop}")
        if prop not in required:
            annotation += " | None"
        lines.append(f"    {prop}: {annotation}{py_field(sub, prop in required)}")
    return lines


def generate_python(spec: dict[str, Any]) -> str:
    defs = spec["defs"]
    out = [
        f'"""{HEADER}"""',
        "",
        "from __future__ import annotations",
        "",
        "from typing import Literal",
        "",
        "from pydantic import BaseModel, ConfigDict, Field",
        "",
        f"PROTOCOL_VERSION = {spec['version']}",
        "",
        "",
        "class ProtocolModel(BaseModel):",
        '    """Base des charges utiles : champs inconnus refusés, instances immuables."""',
        "",
        '    model_config = ConfigDict(extra="forbid", frozen=True)',
        "",
    ]
    for name, sub in defs.items():
        if sub.get("type") == "object":
            out += ["", *py_object(name, sub, defs), ""]
        else:
            out += ["", f"{name} = {py_type(sub, defs, name)}", ""]
    for side in ("client", "server"):
        for msg, sub in spec[side].items():
            out += ["", *py_object(pascal(msg) + "Payload", sub, defs), ""]
    for side in ("client", "server"):
        mapping = ", ".join(f'"{m}": {pascal(m)}Payload' for m in spec[side])
        types = ", ".join(json.dumps(m) for m in spec[side])
        out += [
            "",
            f"{side.capitalize()}MessageType = Literal[{types}]",
            f"{side.upper()}_MESSAGES: dict[str, type[ProtocolModel]] = {{{mapping}}}",
        ]
    return "\n".join(out).replace("\n\n\n\n", "\n\n\n") + "\n"


# ----------------------------------------------------------------------- TypeScript


def ts_type(schema: dict[str, Any], defs: dict[str, Any], where: str) -> str:
    check_keys(schema, where)
    if "$ref" in schema:
        return ref_name(schema["$ref"], defs, where)
    kind = schema.get("type")
    if kind == "string":
        if "enum" in schema:
            return " | ".join(json.dumps(v) for v in schema["enum"])
        return "string"
    if kind in ("integer", "number"):
        return "number"
    if kind == "boolean":
        return "boolean"
    if kind == "array":
        return f"Array<{ts_type(schema['items'], defs, where + '[]')}>"
    raise SchemaError(f"{where}: type non pris en charge {kind!r}")


def ts_object(name: str, schema: dict[str, Any], defs: dict[str, Any]) -> list[str]:
    lines = []
    if "description" in schema:
        lines.append(f"/** {schema['description']} */")
    lines.append(f"export interface {name} {{")
    required = set(schema.get("required", []))
    for prop, sub in schema.get("properties", {}).items():
        if "description" in sub:
            lines.append(f"  /** {sub['description']} */")
        optional = "" if prop in required else "?"
        lines.append(f"  readonly {prop}{optional}: {ts_type(sub, defs, f'{name}.{prop}')};")
    lines.append("}")
    return lines


def generate_typescript(spec: dict[str, Any]) -> str:
    defs = spec["defs"]
    out = [f"// {HEADER}", "", f"export const PROTOCOL_VERSION = {spec['version']};", ""]
    for name, sub in defs.items():
        if sub.get("type") == "object":
            out += [*ts_object(name, sub, defs), ""]
            continue
        if "description" in sub:
            out.append(f"/** {sub['description']} */")
        out += [f"export type {name} = {ts_type(sub, defs, name)};", ""]
    for side in ("client", "server"):
        for msg, sub in spec[side].items():
            out += [*ts_object(pascal(msg) + "Payload", sub, defs), ""]
    for side in ("client", "server"):
        cap = side.capitalize()
        out.append(f"export interface {cap}Payloads {{")
        out += [f"  {m}: {pascal(m)}Payload;" for m in spec[side]]
        out += ["}", "", f"export type {cap}MessageType = keyof {cap}Payloads;", ""]
    out += [
        "/** Message client : `seq` croît à chaque envoi. */",
        "export type ClientMessage = {",
        "  [K in ClientMessageType]: { t: K; seq: number; d: ClientPayloads[K] };",
        "}[ClientMessageType];",
        "",
        "/** Message serveur : `tick` = tick de simulation au moment de l'envoi. */",
        "export type ServerMessage = {",
        "  [K in ServerMessageType]: { t: K; seq: number; tick: number; d: ServerPayloads[K] };",
        "}[ServerMessageType];",
        "",
        "export const SERVER_MESSAGE_TYPES: readonly ServerMessageType[] = ["
        + ", ".join(json.dumps(m) for m in spec["server"])
        + "];",
    ]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------- main


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="vérifie sans écrire")
    args = parser.parse_args()

    spec = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    outputs = {PY_OUT: generate_python(spec), TS_OUT: generate_typescript(spec)}

    stale = [p for p, content in outputs.items() if not p.exists() or p.read_text(encoding="utf-8") != content]
    if args.check:
        for path in stale:
            print(f"Pas à jour : {path.relative_to(ROOT)}", file=sys.stderr)
        if stale:
            print("Lance `python tools/codegen/generate.py`.", file=sys.stderr)
        return 1 if stale else 0

    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"Écrit : {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
