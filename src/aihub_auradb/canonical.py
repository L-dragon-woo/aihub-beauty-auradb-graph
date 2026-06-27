"""Canonicalization for pilot AIHub records.

The real AIHub schemas may vary. This module intentionally accepts common
JSON shapes and quarantines records that cannot be safely mapped.
"""

from __future__ import annotations

import json
import csv
from io import StringIO
from pathlib import Path
from typing import Any

from .ids import sha256_text, stable_id, stable_json
from .models import CanonicalRecord, QuarantineItem, SourceFile


QUESTION_KEYS = ("question", "query", "질문", "문항")
ANSWER_KEYS = ("answer", "response", "답변", "응답")
TEXT_KEYS = ("text", "content", "knowledge", "description", "본문", "내용")
TITLE_KEYS = ("title", "name", "제목")
ID_KEYS = ("id", "record_id", "source_id", "문서id", "문서ID")
NESTED_TITLE_KEYS = (
    ("Data_info", "Title"),
    ("File_info", "File Name"),
)
NESTED_TEXT_KEYS = (
    ("Annotation_info", "Main Keywords"),
    ("File_info", "Purpose"),
    ("File_info", "Cautions"),
    ("Source_info", "Source"),
)


def _first_text(record: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _nested_text(record: dict[str, Any], paths: tuple[tuple[str, str], ...]) -> str:
    values: list[str] = []
    for parent, child in paths:
        nested = record.get(parent)
        if not isinstance(nested, dict):
            continue
        value = nested.get(child)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
        elif value is not None and str(value).strip():
            values.append(str(value).strip())
    return "\n".join(values)


def _records_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("records", "data", "items", "annotations"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]
    return []


def canonicalize_json_payload(
    source_file: SourceFile,
    payload: Any,
) -> tuple[list[CanonicalRecord], list[QuarantineItem]]:
    canonical: list[CanonicalRecord] = []
    quarantine: list[QuarantineItem] = []
    for index, record in enumerate(_records_from_payload(payload)):
        raw_id = _first_text(record, ID_KEYS) or str(index)
        question = _first_text(record, QUESTION_KEYS)
        answer = _first_text(record, ANSWER_KEYS)
        text = _first_text(record, TEXT_KEYS)
        title = _first_text(record, TITLE_KEYS) or _nested_text(record, NESTED_TITLE_KEYS).split("\n")[0]
        nested_text = _nested_text(record, NESTED_TEXT_KEYS)
        record_type = "qa" if question and answer else "document"
        merged_text = "\n".join(part for part in (title, question, answer, text, nested_text) if part)

        if not merged_text.strip():
            quarantine.append(
                QuarantineItem(
                    source_dataset_id=source_file.source_dataset_id,
                    source_file_id=source_file.id,
                    source_record_id=raw_id,
                    reason_code="empty_text",
                    message="No usable text, question, answer, title, or content field found.",
                )
            )
            continue

        canonical.append(
            CanonicalRecord(
                id=stable_id("CanonicalRecord", source_file.id, raw_id, record_type),
                record_type=record_type,
                source_dataset_id=source_file.source_dataset_id,
                source_file_id=source_file.id,
                source_record_id=raw_id,
                text=merged_text,
                title=title,
                question=question,
                answer=answer,
                content_hash=sha256_text(stable_json(record)),
                metadata={"raw_keys": sorted(record.keys())},
            )
        )
    return canonical, quarantine


def canonicalize_json_text(source_file: SourceFile, text: str) -> tuple[list[CanonicalRecord], list[QuarantineItem]]:
    try:
        payload = json.loads(text)
    except Exception as exc:  # noqa: BLE001 - reason is persisted to quarantine.
        return [], [
            QuarantineItem(
                source_dataset_id=source_file.source_dataset_id,
                source_file_id=source_file.id,
                source_record_id="file",
                reason_code="malformed_json",
                message=str(exc),
            )
        ]
    return canonicalize_json_payload(source_file, payload)


def canonicalize_json_file(source_file: SourceFile, absolute_path: Path) -> tuple[list[CanonicalRecord], list[QuarantineItem]]:
    try:
        text = absolute_path.read_text(encoding="utf-8-sig")
    except Exception as exc:  # noqa: BLE001 - reason is persisted to quarantine.
        return [], [
            QuarantineItem(
                source_dataset_id=source_file.source_dataset_id,
                source_file_id=source_file.id,
                source_record_id="file",
                reason_code="malformed_json",
                message=str(exc),
            )
        ]
    return canonicalize_json_text(source_file, text)


def canonicalize_jsonl_text(source_file: SourceFile, text: str) -> tuple[list[CanonicalRecord], list[QuarantineItem]]:
    records: list[CanonicalRecord] = []
    quarantine: list[QuarantineItem] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except Exception as exc:  # noqa: BLE001 - reason is persisted to quarantine.
            quarantine.append(
                QuarantineItem(
                    source_dataset_id=source_file.source_dataset_id,
                    source_file_id=source_file.id,
                    source_record_id=str(line_number),
                    reason_code="malformed_jsonl",
                    message=str(exc),
                )
            )
            continue
        found, failed = canonicalize_json_payload(source_file, payload)
        records.extend(found)
        quarantine.extend(failed)
    return records, quarantine


def canonicalize_manifest(dataset_root: Path, manifest_rows: list[SourceFile]) -> tuple[list[CanonicalRecord], list[QuarantineItem]]:
    records: list[CanonicalRecord] = []
    quarantine: list[QuarantineItem] = []
    for source_file in manifest_rows:
        if source_file.file_type == "csv":
            found, failed = canonicalize_csv_file(source_file, dataset_root / source_file.path)
            records.extend(found)
            quarantine.extend(failed)
            continue
        if source_file.file_type != "json":
            quarantine.append(
                QuarantineItem(
                    source_dataset_id=source_file.source_dataset_id,
                    source_file_id=source_file.id,
                    source_record_id="file",
                    reason_code="unsupported_file_type",
                    message=f"Unsupported file type for canonicalization: {source_file.file_type}",
                )
            )
            continue
        found, failed = canonicalize_json_file(source_file, dataset_root / source_file.path)
        records.extend(found)
        quarantine.extend(failed)
    return records, quarantine


def canonicalize_csv_text(source_file: SourceFile, text: str) -> tuple[list[CanonicalRecord], list[QuarantineItem]]:
    try:
        rows = list(csv.DictReader(StringIO(text)))
    except Exception as exc:  # noqa: BLE001 - reason is persisted to quarantine.
        return [], [
            QuarantineItem(
                source_dataset_id=source_file.source_dataset_id,
                source_file_id=source_file.id,
                source_record_id="file",
                reason_code="malformed_csv",
                message=str(exc),
            )
        ]

    records: list[CanonicalRecord] = []
    quarantine: list[QuarantineItem] = []
    for index, row in enumerate(rows):
        raw_id = row.get("No") or row.get("id") or str(index)
        text_parts = [f"{key}: {value}" for key, value in row.items() if value and str(value).strip()]
        text = "\n".join(text_parts)
        if not text:
            quarantine.append(
                QuarantineItem(
                    source_dataset_id=source_file.source_dataset_id,
                    source_file_id=source_file.id,
                    source_record_id=raw_id,
                    reason_code="empty_text",
                    message="No usable CSV values found.",
                )
            )
            continue
        title = " / ".join(
            part
            for part in (
                row.get("피부 고민 유형", ""),
                row.get("얼굴 피부 타입", ""),
                row.get("고민부위", ""),
            )
            if part
        )
        records.append(
            CanonicalRecord(
                id=stable_id("CanonicalRecord", source_file.id, raw_id, "survey"),
                record_type="survey",
                source_dataset_id=source_file.source_dataset_id,
                source_file_id=source_file.id,
                source_record_id=raw_id,
                text=text,
                title=title,
                content_hash=sha256_text(stable_json(row)),
                metadata={"raw_keys": sorted(row.keys())},
            )
        )
    return records, quarantine


def canonicalize_csv_file(source_file: SourceFile, absolute_path: Path) -> tuple[list[CanonicalRecord], list[QuarantineItem]]:
    try:
        text = absolute_path.read_text(encoding="utf-8-sig")
    except Exception as exc:  # noqa: BLE001 - reason is persisted to quarantine.
        return [], [
            QuarantineItem(
                source_dataset_id=source_file.source_dataset_id,
                source_file_id=source_file.id,
                source_record_id="file",
                reason_code="malformed_csv",
                message=str(exc),
            )
        ]
    return canonicalize_csv_text(source_file, text)
