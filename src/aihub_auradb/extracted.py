"""Build artifacts from extracted AIHub files."""

from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

from .canonical import canonicalize_csv_file, canonicalize_json_file, canonicalize_jsonl_text
from .ids import stable_id
from .io import write_jsonl
from .models import CanonicalRecord, QuarantineItem, SourceFile
from .quality import build_quality_report
from .zipbatch import CANONICAL_EXTENSIONS, infer_dataset_id


@dataclass(frozen=True)
class ExtractSummary:
    zip_files: int
    files: int
    output_dir: str

    def to_dict(self) -> dict[str, int | str]:
        return asdict(self)


@dataclass(frozen=True)
class ExtractedBuildSummary:
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


def _safe_extract_path(base: Path, relative_name: str) -> Path:
    target = (base / relative_name).resolve()
    base_resolved = base.resolve()
    if not str(target).startswith(str(base_resolved)):
        raise ValueError(f"Unsafe zip entry path: {relative_name}")
    return target


def _safe_entry_name(name: str) -> PurePosixPath:
    entry = PurePosixPath(name.replace("\\", "/"))
    safe_parts = [part for part in entry.parts if part not in ("", "/", ".", "..")]
    if not safe_parts:
        raise ValueError(f"Unsafe zip entry path: {name}")
    return PurePosixPath(*safe_parts)


def _short_file_name(path: PurePosixPath, max_length: int = 120) -> PurePosixPath:
    parent = PurePosixPath(*path.parts[:-1]) if len(path.parts) > 1 else PurePosixPath()
    name = path.name
    if len(name) <= max_length:
        return parent / name
    suffix = PurePosixPath(name).suffix
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:12]
    stem_limit = max_length - len(suffix) - len(digest) - 1
    shortened = f"{PurePosixPath(name).stem[:stem_limit]}_{digest}{suffix}"
    return parent / shortened


def extract_zip_tree(root: Path, output_dir: Path) -> ExtractSummary:
    root = root.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_count = 0
    file_count = 0
    for zip_path in sorted(root.rglob("*.zip")):
        zip_count += 1
        zip_key = hashlib.sha256(zip_path.relative_to(root).as_posix().encode("utf-8")).hexdigest()[:10]
        zip_dir = PurePosixPath(infer_dataset_id(zip_path)) / f"{zip_path.stem}_{zip_key}"
        with zipfile.ZipFile(zip_path) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                entry_name = _short_file_name(_safe_entry_name(info.filename))
                target = _safe_extract_path(output_dir, (zip_dir / entry_name).as_posix())
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as dest:
                    dest.write(source.read())
                file_count += 1
    return ExtractSummary(zip_files=zip_count, files=file_count, output_dir=str(output_dir))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_file(root: Path, path: Path, manifest_version: str) -> SourceFile:
    rel = path.relative_to(root).as_posix()
    dataset_id = infer_dataset_id(path)
    return SourceFile(
        id=stable_id("SourceFile", dataset_id, rel),
        source_dataset_id=dataset_id,
        path=rel,
        sha256=_sha256_file(path),
        size_bytes=path.stat().st_size,
        file_type=path.suffix.lower().lstrip(".") or "unknown",
        manifest_version=manifest_version,
    )


def _canonicalize_file(source_file: SourceFile, path: Path) -> tuple[list[CanonicalRecord], list[QuarantineItem]]:
    if source_file.file_type == "json":
        return canonicalize_json_file(source_file, path)
    if source_file.file_type == "csv":
        return canonicalize_csv_file(source_file, path)
    if source_file.file_type == "jsonl":
        try:
            return canonicalize_jsonl_text(source_file, path.read_text(encoding="utf-8-sig"))
        except Exception as exc:  # noqa: BLE001 - reason is persisted to quarantine.
            return [], [
                QuarantineItem(
                    source_dataset_id=source_file.source_dataset_id,
                    source_file_id=source_file.id,
                    source_record_id="file",
                    reason_code="malformed_jsonl",
                    message=str(exc),
                )
            ]
    return [], []


def canonicalize_extracted_tree(
    root: Path,
    output_dir: Path,
    batch_size: int = 1000,
    manifest_version: str = "extracted-full",
) -> ExtractedBuildSummary:
    root = root.resolve()
    records_dir = output_dir / "records"
    manifest_output = output_dir / "manifest_full_extracted.jsonl"
    quarantine_output = output_dir / "quarantine_full_extracted.jsonl"
    quality_output = output_dir / "quality_full_extracted.json"
    records_dir.mkdir(parents=True, exist_ok=True)

    manifest_rows: list[SourceFile] = []
    records_for_quality: list[CanonicalRecord] = []
    quarantine: list[QuarantineItem] = []
    current_batch: list[dict[str, object]] = []
    canonical_files = 0
    record_count = 0
    batch_count = 0

    def flush_batch() -> None:
        nonlocal batch_count, current_batch
        if not current_batch:
            return
        batch_count += 1
        write_jsonl(records_dir / f"records_{batch_count:06d}.jsonl", current_batch)
        current_batch = []

    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        source_file = _source_file(root, path, manifest_version)
        manifest_rows.append(source_file)
        if path.suffix.lower() in CANONICAL_EXTENSIONS:
            canonical_files += 1
            found, failed = _canonicalize_file(source_file, path)
            quarantine.extend(failed)
            records_for_quality.extend(found)
            for record in found:
                current_batch.append(record.to_dict())
                record_count += 1
                if len(current_batch) >= batch_size:
                    flush_batch()

    flush_batch()
    write_jsonl(manifest_output, [row.to_dict() for row in manifest_rows])
    write_jsonl(quarantine_output, [item.to_dict() for item in quarantine])
    quality_output.write_text(
        json.dumps(build_quality_report(records_for_quality, quarantine).to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return ExtractedBuildSummary(
        source_files=len(manifest_rows),
        canonical_files=canonical_files,
        records=record_count,
        quarantine=len(quarantine),
        batches=batch_count,
        manifest_output=str(manifest_output),
        records_dir=str(records_dir),
        quarantine_output=str(quarantine_output),
        quality_output=str(quality_output),
    )
