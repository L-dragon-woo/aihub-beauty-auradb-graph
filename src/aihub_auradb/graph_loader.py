"""AuraDB pilot loader for canonical AIHub records."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase

from .io import read_jsonl
from .schema import schema_cypher

IMAGE_FILE_TYPES = {"jpg", "jpeg", "png", "webp", "bmp", "gif"}


@dataclass(frozen=True)
class LoadSummary:
    datasets: int
    source_files: int
    documents: int
    chunks: int
    qa: int

    def to_dict(self) -> dict[str, int]:
        return {
            "datasets": self.datasets,
            "source_files": self.source_files,
            "documents": self.documents,
            "chunks": self.chunks,
            "qa": self.qa,
        }


@dataclass(frozen=True)
class BatchLoadSummary:
    source_files: int
    batches: int
    documents: int
    chunks: int
    qa: int
    images: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "source_files": self.source_files,
            "batches": self.batches,
            "documents": self.documents,
            "chunks": self.chunks,
            "qa": self.qa,
            "images": self.images,
        }


def split_cypher(script: str) -> list[str]:
    return [statement.strip() for statement in script.split(";") if statement.strip()]


def apply_schema(uri: str, username: str, password: str, database: str, include_vector: bool = False) -> int:
    statements = split_cypher(schema_cypher(include_vector=include_vector))
    with GraphDatabase.driver(uri, auth=(username, password)) as driver:
        driver.verify_connectivity()
        with driver.session(database=database) as session:
            for statement in statements:
                session.run(statement).consume()
    return len(statements)


def _dataset_name(dataset_id: str) -> str:
    return {
        "71961": "problematic-skin makeup recommendation data",
        "71886": "skincare ingredient-effect recommendation data",
    }.get(dataset_id, f"AIHub {dataset_id}")


def _read_source_files(manifest_paths: list[Path]) -> dict[str, dict[str, Any]]:
    source_files: dict[str, dict[str, Any]] = {}
    for path in manifest_paths:
        for row in read_jsonl(path):
            source_files[row["id"]] = row
    return source_files


def _read_records(record_paths: list[Path], limit: int | None = None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in record_paths:
        records.extend(read_jsonl(path))
    if limit is not None:
        records = records[:limit]
    return records


def _validate_record_sources(records: list[dict[str, Any]], source_files: dict[str, dict[str, Any]]) -> None:
    missing_source_file_ids = sorted({record["source_file_id"] for record in records} - set(source_files))
    if missing_source_file_ids:
        preview = ", ".join(missing_source_file_ids[:5])
        suffix = "..." if len(missing_source_file_ids) > 5 else ""
        raise ValueError(f"Records reference missing manifest source_file_id values: {preview}{suffix}")


def _merge_source_files(session: Any, source_files: dict[str, dict[str, Any]], build_id: str) -> None:
    dataset_ids = sorted({row["source_dataset_id"] for row in source_files.values()})
    for dataset_id in dataset_ids:
        session.run(
            """
MERGE (d:Dataset {id: $id})
SET d.name = $name,
    d.aihub_dataset_sn = $id,
    d.source_url = $source_url,
    d.manifest_version = $manifest_version,
    d.build_id = $build_id
""",
            {
                "id": dataset_id,
                "name": _dataset_name(dataset_id),
                "source_url": f"https://aihub.or.kr/aihubdata/data/view.do?aihubDataSe=data&dataSetSn={dataset_id}",
                "manifest_version": "local",
                "build_id": build_id,
            },
        ).consume()

    for source in source_files.values():
        session.run(
            """
MATCH (d:Dataset {id: $source_dataset_id})
MERGE (s:SourceFile {id: $id})
SET s.path = $path,
    s.sha256 = $sha256,
    s.size_bytes = $size_bytes,
    s.file_type = $file_type,
    s.source_dataset_id = $source_dataset_id,
    s.manifest_version = $manifest_version,
    s.build_id = $build_id
MERGE (s)-[:FROM_DATASET {id: $rel_id, build_id: $build_id}]->(d)
""",
            {**source, "build_id": build_id, "rel_id": f"{source['id']}|FROM_DATASET|{source['source_dataset_id']}"},
        ).consume()


def _image_sources(source_files: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [source for source in source_files.values() if str(source.get("file_type", "")).lower() in IMAGE_FILE_TYPES]


def _merge_images(session: Any, source_files: dict[str, dict[str, Any]], build_id: str) -> int:
    image_sources = _image_sources(source_files)
    for source in image_sources:
        image_id = f"Image:{source['id']}"
        session.run(
            """
MATCH (s:SourceFile {id: $source_file_id})
MERGE (img:Image {id: $image_id})
SET img.path = $path,
    img.sha256 = $sha256,
    img.size_bytes = $size_bytes,
    img.file_type = $file_type,
    img.source_dataset_id = $source_dataset_id,
    img.source_file_id = $source_file_id,
    img.build_id = $build_id,
    img.extraction_method = 'zip_manifest',
    img.confidence = 1.0
MERGE (img)-[:FROM_FILE {id: $rel_id, build_id: $build_id}]->(s)
""",
            {
                **source,
                "image_id": image_id,
                "source_file_id": source["id"],
                "build_id": build_id,
                "rel_id": f"{image_id}|FROM_FILE|{source['id']}",
            },
        ).consume()
    return len(image_sources)


def _merge_records(session: Any, records: list[dict[str, Any]], build_id: str) -> None:
    for record in records:
        document_id = f"Document:{record['id']}"
        chunk_id = f"Chunk:{record['id']}:0"
        params = {
            **record,
            "document_id": document_id,
            "chunk_id": chunk_id,
            "build_id": build_id,
            "rel_file_id": f"{document_id}|FROM_FILE|{record['source_file_id']}",
            "rel_chunk_id": f"{chunk_id}|PART_OF|{document_id}",
        }
        session.run(
            """
MATCH (s:SourceFile {id: $source_file_id})
MERGE (doc:Document {id: $document_id})
SET doc.document_type = $record_type,
    doc.title = $title,
    doc.raw_id = $source_record_id,
    doc.language = 'ko',
    doc.source_dataset_id = $source_dataset_id,
    doc.source_file_id = $source_file_id,
    doc.source_record_id = $source_record_id,
    doc.content_hash = $content_hash,
    doc.extraction_method = $extraction_method,
    doc.confidence = $confidence,
    doc.build_id = $build_id
MERGE (doc)-[:FROM_FILE {id: $rel_file_id, build_id: $build_id}]->(s)
MERGE (chunk:Chunk {id: $chunk_id})
SET chunk.text = $text,
    chunk.chunk_index = 0,
    chunk.token_count = size(split($text, ' ')),
    chunk.chunking_method = 'record_as_chunk',
    chunk.source_document_id = $document_id,
    chunk.source_dataset_id = $source_dataset_id,
    chunk.source_file_id = $source_file_id,
    chunk.source_record_id = $source_record_id,
    chunk.content_hash = $content_hash,
    chunk.extraction_method = $extraction_method,
    chunk.confidence = $confidence,
    chunk.build_id = $build_id
MERGE (chunk)-[:PART_OF {id: $rel_chunk_id, build_id: $build_id}]->(doc)
""",
            params,
        ).consume()

        if record.get("record_type") == "qa":
            session.run(
                """
MATCH (doc:Document {id: $document_id})
MATCH (chunk:Chunk {id: $chunk_id})
MERGE (qa:QA {id: $id})
SET qa.question = $question,
    qa.answer = $answer,
    qa.qa_type = 'source',
    qa.source_document_id = $document_id,
    qa.source_dataset_id = $source_dataset_id,
    qa.source_file_id = $source_file_id,
    qa.source_record_id = $source_record_id,
    qa.extraction_method = $extraction_method,
    qa.confidence = $confidence,
    qa.build_id = $build_id
MERGE (qa)-[:PART_OF {id: $id + '|PART_OF|' + $document_id, build_id: $build_id}]->(doc)
MERGE (qa)-[:SUPPORTED_BY {id: $id + '|SUPPORTED_BY|' + $chunk_id, build_id: $build_id}]->(chunk)
""",
                params,
            ).consume()


def load_canonical_records(
    uri: str,
    username: str,
    password: str,
    database: str,
    manifest_paths: list[Path],
    record_paths: list[Path],
    build_id: str,
    limit: int | None = None,
    load_sources: bool = True,
) -> LoadSummary:
    source_files = _read_source_files(manifest_paths)
    records = _read_records(record_paths, limit)
    _validate_record_sources(records, source_files)
    dataset_ids = sorted({row["source_dataset_id"] for row in source_files.values()} | {r["source_dataset_id"] for r in records})

    with GraphDatabase.driver(uri, auth=(username, password)) as driver:
        driver.verify_connectivity()
        with driver.session(database=database) as session:
            if load_sources:
                _merge_source_files(session, source_files, build_id)
            _merge_records(session, records, build_id)

    return LoadSummary(
        datasets=len(dataset_ids),
        source_files=len(source_files),
        documents=len(records),
        chunks=len(records),
        qa=sum(1 for record in records if record.get("record_type") == "qa"),
    )


def load_record_batches(
    uri: str,
    username: str,
    password: str,
    database: str,
    manifest_path: Path,
    records_dir: Path,
    build_id: str,
    load_images: bool = False,
) -> BatchLoadSummary:
    source_files = _read_source_files([manifest_path])
    record_paths = sorted(records_dir.glob("*.jsonl"))
    total_documents = 0
    total_qa = 0
    total_images = 0
    with GraphDatabase.driver(uri, auth=(username, password)) as driver:
        driver.verify_connectivity()
        with driver.session(database=database) as session:
            _merge_source_files(session, source_files, build_id)
            if load_images:
                total_images = _merge_images(session, source_files, build_id)
            for path in record_paths:
                records = _read_records([path])
                _validate_record_sources(records, source_files)
                _merge_records(session, records, build_id)
                total_documents += len(records)
                total_qa += sum(1 for record in records if record.get("record_type") == "qa")
    return BatchLoadSummary(
        source_files=len(source_files),
        batches=len(record_paths),
        documents=total_documents,
        chunks=total_documents,
        qa=total_qa,
        images=total_images,
    )


def load_images_from_manifest(
    uri: str,
    username: str,
    password: str,
    database: str,
    manifest_path: Path,
    build_id: str,
) -> int:
    source_files = _read_source_files([manifest_path])
    with GraphDatabase.driver(uri, auth=(username, password)) as driver:
        driver.verify_connectivity()
        with driver.session(database=database) as session:
            return _merge_images(session, source_files, build_id)


def verify_counts(uri: str, username: str, password: str, database: str) -> dict[str, int]:
    labels = ["Dataset", "SourceFile", "Image", "Document", "Chunk", "QA"]
    counts: dict[str, int] = {}
    with GraphDatabase.driver(uri, auth=(username, password)) as driver:
        driver.verify_connectivity()
        with driver.session(database=database) as session:
            for label in labels:
                result = session.run(f"MATCH (n:{label}) RETURN count(n) AS count").single()
                counts[label] = int(result["count"]) if result else 0
            orphan = session.run(
                """
MATCH (c:Chunk)
WHERE NOT (c)-[:PART_OF]->(:Document)
RETURN count(c) AS count
"""
            ).single()
            missing_provenance = session.run(
                """
MATCH (n)
WHERE (n:Document OR n:Chunk OR n:QA)
  AND (n.source_dataset_id IS NULL OR n.source_file_id IS NULL OR n.source_record_id IS NULL)
RETURN count(n) AS count
"""
            ).single()
            counts["OrphanChunk"] = int(orphan["count"]) if orphan else 0
            counts["MissingProvenance"] = int(missing_provenance["count"]) if missing_provenance else 0
    return counts
