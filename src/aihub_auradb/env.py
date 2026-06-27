"""Environment loading without exposing secrets."""

from __future__ import annotations

import os
from pathlib import Path


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        values[key.strip()] = value
    return values


def allow_self_signed_scheme(uri: str) -> str:
    replacements = {
        "neo4j+s://": "neo4j+ssc://",
        "bolt+s://": "bolt+ssc://",
    }
    for source, target in replacements.items():
        if uri.startswith(source):
            return target + uri[len(source) :]
    return uri


def neo4j_config(env_path: Path = Path(".env"), allow_self_signed: bool = False) -> dict[str, str]:
    file_values = load_env_file(env_path)

    def pick(*names: str, default: str = "") -> str:
        for name in names:
            value = os.environ.get(name) or file_values.get(name)
            if value:
                return value
        return default

    config = {
        "uri": pick("NEO4J_URI", "AURA_URI", "NEO4J_CONNECTION_URI"),
        "username": pick("NEO4J_USERNAME", "NEO4J_USER", "AURA_USERNAME", "AURA_USER"),
        "password": pick("NEO4J_PASSWORD", "AURA_PASSWORD"),
        "database": pick("NEO4J_DATABASE", "AURA_DATABASE", default="neo4j"),
    }
    missing = [key for key, value in config.items() if key != "database" and not value]
    if missing:
        raise ValueError(f"Missing Neo4j config values: {', '.join(missing)}")
    if allow_self_signed:
        config["uri"] = allow_self_signed_scheme(config["uri"])
    return config
