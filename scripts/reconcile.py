#!/usr/bin/env python3
"""Merge repository Codex settings into ~/.codex without losing local state."""

import json
import os
import re
import shutil
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODEX_DIR = Path(os.environ.get("CODEX_DIR", Path.home() / ".codex"))


def merge(dest, source):
    if isinstance(dest, dict) and isinstance(source, dict):
        return {
            key: merge(dest.get(key), value)
            for key, value in {**dest, **source}.items()
        }
    return source


def toml_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(
            f"{toml_key(key)} = {toml_value(item)}" for key, item in value.items()
        ) + " }"
    raise TypeError(f"unsupported TOML value: {type(value).__name__}")


def toml_key(key):
    return key if re.fullmatch(r"[A-Za-z0-9_-]+", key) else json.dumps(key)


def dump_toml(data):
    lines = []

    def emit(table, prefix=()):
        scalars = {
            key: value for key, value in table.items() if not isinstance(value, dict)
        }
        children = {
            key: value for key, value in table.items() if isinstance(value, dict)
        }
        for key, value in scalars.items():
            lines.append(f"{toml_key(key)} = {toml_value(value)}")
        for key, value in children.items():
            if lines and lines[-1] != "":
                lines.append("")
            name = ".".join(toml_key(part) for part in (*prefix, key))
            lines.append(f"[{name}]")
            emit(value, (*prefix, key))

    emit(data)
    return "\n".join(lines) + "\n"


def load_toml(path):
    text = path.read_text(encoding="utf-8")
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        # Codex has emitted multiline inline tables; TOML requires those to
        # remain on one line. Normalize that narrow legacy shape before merge.
        text = re.sub(
            r"=\s*\{\s*([\w-]+)\s*=\s*\{\s*([^{}]+?)\s*\}\s*\}",
            r"= { \1 = { \2 } }",
            text,
            flags=re.DOTALL,
        )
        return tomllib.loads(text)


def reconcile_file(source, destination):
    source_data = load_toml(source)
    destination_data = (
        load_toml(destination)
        if destination.exists()
        else {}
    )
    merged = merge(destination_data, source_data)
    text = dump_toml(merged)
    if destination.exists() and destination.read_text(encoding="utf-8") == text:
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
    return True


def main():
    CODEX_DIR.mkdir(parents=True, exist_ok=True)
    changed = reconcile_file(ROOT / "codex/config.toml", CODEX_DIR / "config.toml")
    source = ROOT / "codex/hooks.json"
    destination = CODEX_DIR / "hooks.json"
    if not destination.exists() or json.loads(destination.read_text()) != json.loads(
        source.read_text()
    ):
        shutil.copy2(source, destination)
        changed = True
    print("Codex config updated." if changed else "Codex config already in sync.")


if __name__ == "__main__":
    main()
