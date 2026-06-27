"""Shared data contracts for the DB construction pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceFile:
    id: str
    source_dataset_id: str
    path: str
    sha256: str
    size_bytes: int
    file_type: str
    manifest_version: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CanonicalRecord:
    id: str
    record_type: str
    source_dataset_id: str
    source_file_id: str
    source_record_id: str
    text: str
    title: str = ""
    question: str = ""
    answer: str = ""
    content_hash: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    extraction_method: str = "source"
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QuarantineItem:
    source_dataset_id: str
    source_file_id: str
    source_record_id: str
    reason_code: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
