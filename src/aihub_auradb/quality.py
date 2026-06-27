"""Data quality checks for canonical records and graph-readiness artifacts."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass

from .models import CanonicalRecord, QuarantineItem


@dataclass(frozen=True)
class QualityReport:
    total_records: int
    duplicate_ids: int
    empty_text_records: int
    missing_provenance_records: int
    quarantine_count: int
    failure_reasons: dict[str, int]
    record_type_counts: dict[str, int]
    passed: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_quality_report(records: list[CanonicalRecord], quarantine: list[QuarantineItem]) -> QualityReport:
    ids = [record.id for record in records]
    counts = Counter(ids)
    duplicate_ids = sum(count - 1 for count in counts.values() if count > 1)
    empty_text = sum(1 for record in records if not record.text.strip())
    missing_provenance = sum(
        1
        for record in records
        if not record.source_dataset_id or not record.source_file_id or not record.source_record_id
    )
    type_counts = Counter(record.record_type for record in records)
    failure_reasons = Counter(item.reason_code for item in quarantine)
    passed = (
        len(records) > 0
        and duplicate_ids == 0
        and empty_text == 0
        and missing_provenance == 0
    )
    return QualityReport(
        total_records=len(records),
        duplicate_ids=duplicate_ids,
        empty_text_records=empty_text,
        missing_provenance_records=missing_provenance,
        quarantine_count=len(quarantine),
        failure_reasons=dict(sorted(failure_reasons.items())),
        record_type_counts=dict(sorted(type_counts.items())),
        passed=passed,
    )
