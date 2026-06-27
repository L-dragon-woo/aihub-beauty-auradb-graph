"""Canonicalize AIHub zip archives without extracting them to disk."""

from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path

from .canonical import canonicalize_csv_text, canonicalize_json_text, canonicalize_jsonl_text
from .ids import stable_id
from .io import write_jsonl
from .models import CanonicalRecord, QuarantineItem, SourceFile
from .quality import build_quality_report


CANONICAL_EXTENSIONS = {".csv", ".json", ".jsonl"}
DATASET_PREFIXES = {
    "02.": "71961",
    "03.": "71886",
}


@dataclass(frozen=True)
class ZipBatchSummary:
    zip_files: int
    source_files: int
    canonical_files: int
    records: int
    quarantine: int
    batches: int
    manifest_output: str
    records_dir: str
    quarantine_output: str
    quality_output: str

    def to_dict(self) -> dict[str, int | str]:
        return asdict(self)


def infer_dataset_id(path: Path) -> str:
    parts = path.parts
    for part in parts:
        for prefix, dataset_id in DATASET_PREFIXES.items():
            if part.startswith(prefix):
                return dataset_id
    text = str(path)
    for dataset_id in ("71961", "71886"):
        if dataset_id in text:
            return dataset_id
    return "unknown"


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp949"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _entry_source_file(root: Path, zip_path: Path, info: zipfile.ZipInfo, data: bytes, manifest_version: str) -> SourceFile:
    dataset_id = infer_dataset_id(zip_path)
    rel_zip = zip_path.relative_to(root).as_posix()
    entry_path = f"{rel_zip}::{info.filename}"
    return SourceFile(
        id=stable_id("SourceFile", dataset_id, entry_path),
        source_dataset_id=dataset_id,
        path=entry_path,
        sha256=hashlib.sha256(data).hexdigest(),
        size_bytes=info.file_size,
        file_type=Path(info.filename).suffix.lower().lstrip(".") or "unknown",
        manifest_version=manifest_version,
    )


def _canonicalize_entry(source_file: SourceFile, text: str) -> tuple[list[CanonicalRecord], list[QuarantineItem]]:
    if source_file.file_type == "json":
        return canonicalize_json_text(source_file, text)
    if source_file.file_type == "jsonl":
        return canonicalize_jsonl_text(source_file, text)
    if source_file.file_type == "csv":
        return canonicalize_csv_text(source_file, text)
    return [], []


def canonicalize_zip_tree(
    root: Path,
    output_dir: Path,
    batch_size: int = 1000,
    manifest_version: str = "zip-full",
    max_entries: int | None = None,
) -> ZipBatchSummary:
    root = root.resolve()
    records_dir = output_dir / "records"
    manifest_output = output_dir / "manifest_full.jsonl"
    quarantine_output = output_dir / "quarantine_full.jsonl"
    quality_output = output_dir / "quality_full.json"
    records_dir.mkdir(parents=True, exist_ok=True)

    manifest_rows: list[SourceFile] = []
    quarantine: list[QuarantineItem] = []
    records_for_quality: list[CanonicalRecord] = []
    current_batch: list[dict[str, object]] = []
    batch_count = 0
    source_file_count = 0
    canonical_file_count = 0
    zip_count = 0
    record_count = 0

    def flush_batch() -> None:
        nonlocal batch_count, current_batch
        if not current_batch:
            return
        batch_count += 1
        write_jsonl(records_dir / f"records_{batch_count:06d}.jsonl", current_batch)
        current_batch = []

    processed_entries = 0
    for zip_path in sorted(root.rglob("*.zip")):
        zip_count += 1
        with zipfile.ZipFile(zip_path) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                if max_entries is not None and processed_entries >= max_entries:
                    break
                with archive.open(info) as handle:
                    data = handle.read()
                source_file = _entry_source_file(root, zip_path, info, data, manifest_version)
                manifest_rows.append(source_file)
                source_file_count += 1
                suffix = Path(info.filename).suffix.lower()
                if suffix in CANONICAL_EXTENSIONS:
                    canonical_file_count += 1
                    found, failed = _canonicalize_entry(source_file, _decode_text(data))
                    quarantine.extend(failed)
                    records_for_quality.extend(found)
                    for record in found:
                        current_batch.append(record.to_dict())
                        record_count += 1
                        if len(current_batch) >= batch_size:
                            flush_batch()
                processed_entries += 1
            if max_entries is not None and processed_entries >= max_entries:
                break

    flush_batch()
    write_jsonl(manifest_output, [row.to_dict() for row in manifest_rows])
    write_jsonl(quarantine_output, [item.to_dict() for item in quarantine])
    quality_output.write_text(
        json.dumps(build_quality_report(records_for_quality, quarantine).to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return ZipBatchSummary(
        zip_files=zip_count,
        source_files=source_file_count,
        canonical_files=canonical_file_count,
        records=record_count,
        quarantine=len(quarantine),
        batches=batch_count,
        manifest_output=str(manifest_output),
        records_dir=str(records_dir),
        quarantine_output=str(quarantine_output),
        quality_output=str(quality_output),
    )
