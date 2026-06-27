"""Zip scan and sampling helpers for large AIHub downloads."""

from __future__ import annotations

import json
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from .ids import sha256_file


TEXT_EXTENSIONS = {".json", ".jsonl", ".csv", ".txt", ".xml", ".xlsx", ".xls"}


@dataclass(frozen=True)
class ZipScan:
    zip_path: str
    sha256: str
    size_bytes: int
    entries: int
    total_uncompressed_bytes: int
    extension_counts: dict[str, int]
    extension_bytes: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def scan_zip(path: Path) -> ZipScan:
    extension_counts: Counter[str] = Counter()
    extension_bytes: Counter[str] = Counter()
    total_uncompressed = 0
    entries = 0

    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            entries += 1
            suffix = Path(info.filename).suffix.lower() or "<none>"
            extension_counts[suffix] += 1
            extension_bytes[suffix] += info.file_size
            total_uncompressed += info.file_size

    return ZipScan(
        zip_path=str(path),
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
        entries=entries,
        total_uncompressed_bytes=total_uncompressed,
        extension_counts=dict(sorted(extension_counts.items())),
        extension_bytes=dict(sorted(extension_bytes.items())),
    )


def scan_zip_tree(root: Path) -> list[ZipScan]:
    return [scan_zip(path) for path in sorted(root.rglob("*.zip"))]


def write_scan_report(root: Path, output: Path) -> list[ZipScan]:
    scans = scan_zip_tree(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps([scan.to_dict() for scan in scans], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return scans


def sample_zip_entries(zip_path: Path, output_dir: Path, limit: int, extensions: set[str] | None = None) -> list[Path]:
    extensions = extensions or TEXT_EXTENSIONS
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            if len(written) >= limit:
                break
            if info.is_dir():
                continue
            suffix = Path(info.filename).suffix.lower()
            if suffix not in extensions:
                continue
            target = output_dir / Path(info.filename).name
            if target.exists():
                stem = target.stem
                target = target.with_name(f"{stem}_{len(written)}{target.suffix}")
            with archive.open(info) as source, target.open("wb") as dest:
                dest.write(source.read())
            written.append(target)
    return written

