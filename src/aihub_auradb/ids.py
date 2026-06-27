"""Deterministic IDs and lightweight Korean/domain normalization helpers."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


_NON_ID = re.compile(r"[^0-9a-zA-Z가-힣]+")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def slug(value: str) -> str:
    cleaned = _NON_ID.sub("-", value.strip().lower()).strip("-")
    return cleaned or "unknown"


def stable_id(label: str, *parts: object, max_hash: int = 16) -> str:
    raw = "|".join(str(part) for part in parts if part is not None and str(part) != "")
    digest = sha256_text(raw)[:max_hash]
    readable = slug(str(parts[0])) if parts else "item"
    return f"{label}:{readable}:{digest}"


def normalize_term(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())

