"""Raw file manifest generation."""

from __future__ import annotations

from pathlib import Path

from .ids import stable_id, sha256_file
from .models import SourceFile


IGNORED_DIRS = {".git", ".omx", ".omc", "__pycache__", ".pytest_cache"}


def iter_source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        files.append(path)
    return sorted(files)


def build_manifest(dataset_root: Path, dataset_id: str, manifest_version: str = "local") -> list[SourceFile]:
    dataset_root = dataset_root.resolve()
    rows: list[SourceFile] = []
    for path in iter_source_files(dataset_root):
        rel = path.relative_to(dataset_root).as_posix()
        rows.append(
            SourceFile(
                id=stable_id("SourceFile", dataset_id, rel),
                source_dataset_id=dataset_id,
                path=rel,
                sha256=sha256_file(path),
                size_bytes=path.stat().st_size,
                file_type=path.suffix.lower().lstrip(".") or "unknown",
                manifest_version=manifest_version,
            )
        )
    return rows

