"""Schema profiling for staged AIHub-like JSON files."""

from __future__ import annotations

import json
import csv
from collections import Counter
from pathlib import Path
from typing import Any


def _records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("records", "data", "items", "annotations"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]
    return []


def profile_json_files(paths: list[Path], sample_limit: int = 100) -> dict[str, Any]:
    key_counts: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()
    sampled = 0
    files_read = 0
    failed_files: list[dict[str, str]] = []
    skipped_files = 0

    for path in paths:
        if sampled >= sample_limit:
            break
        if path.suffix.lower() == ".csv":
            files_read += 1
            try:
                with path.open("r", encoding="utf-8-sig", newline="") as handle:
                    reader = csv.DictReader(handle)
                    for record in reader:
                        if sampled >= sample_limit:
                            break
                        sampled += 1
                        for key, value in record.items():
                            key_counts[key] += 1
                            type_counts[f"{key}:{type(value).__name__}"] += 1
            except Exception as exc:  # noqa: BLE001 - reported in profile artifact.
                failed_files.append({"path": str(path), "error": str(exc)})
            continue
        if path.suffix.lower() != ".json":
            skipped_files += 1
            continue
        files_read += 1
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception as exc:  # noqa: BLE001 - reported in profile artifact.
            failed_files.append({"path": str(path), "error": str(exc)})
            continue
        for record in _records(payload):
            if sampled >= sample_limit:
                break
            sampled += 1
            for key, value in record.items():
                key_counts[key] += 1
                type_counts[f"{key}:{type(value).__name__}"] += 1

    return {
        "files_read": files_read,
        "failed_files": failed_files,
        "skipped_files": skipped_files,
        "records_sampled": sampled,
        "key_counts": dict(sorted(key_counts.items())),
        "type_counts": dict(sorted(type_counts.items())),
    }
