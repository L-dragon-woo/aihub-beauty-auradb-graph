"""Machine-readable graph property contracts."""

from __future__ import annotations


COMMON_NODE_PROPERTIES = [
    "id",
    "source_dataset_id",
    "source_file_id",
    "source_record_id",
    "source_version",
    "build_id",
    "created_at",
    "updated_at",
    "extraction_method",
    "confidence",
]

NODE_PROPERTY_CONTRACTS: dict[str, list[str]] = {
    "Dataset": ["id", "name", "aihub_dataset_sn", "source_url", "license_or_access_note", "manifest_version"],
    "SourceFile": ["id", "path", "sha256", "size_bytes", "file_type", "source_dataset_id", "manifest_version"],
    "Image": ["id", "path", "sha256", "size_bytes", "file_type", "source_file_id", "source_dataset_id"],
    "Document": ["id", "document_type", "title", "raw_id", "language", "source_file_id"],
    "Chunk": ["id", "text", "chunk_index", "token_count", "chunking_method", "source_document_id"],
    "QA": ["id", "question", "answer", "qa_type", "source_document_id"],
    "Ingredient": ["id", "canonical_name_ko", "aliases", "normalization_status"],
    "SkinConcern": ["id", "canonical_name_ko", "aliases", "taxonomy_status"],
    "SkinType": ["id", "canonical_name_ko", "aliases", "taxonomy_status"],
    "SkinCondition": ["id", "canonical_name_ko", "aliases", "taxonomy_status"],
    "FaceRegion": ["id", "canonical_name_ko", "aliases", "taxonomy_status"],
    "Effect": ["id", "canonical_name_ko", "aliases", "taxonomy_status"],
    "Caution": ["id", "canonical_name_ko", "aliases", "taxonomy_status"],
    "ExternalFactor": ["id", "canonical_name_ko", "aliases", "taxonomy_status"],
    "Recommendation": ["id", "recommendation_type", "text", "source_document_id", "source_qa_id", "confidence"],
    "Evidence": ["id", "text", "evidence_type", "source_document_id", "source_chunk_id", "source_qa_id"],
}

RELATIONSHIP_PROPERTIES = [
    "id",
    "source_dataset_id",
    "source_file_id",
    "source_document_id",
    "source_chunk_id",
    "source_qa_id",
    "extraction_method",
    "confidence",
    "candidate",
    "build_id",
    "created_at",
    "updated_at",
]

EMBEDDING_PROPERTIES = [
    "embedding_model",
    "embedding_dimensions",
    "embedding_version",
    "embedding_source_text_hash",
    "embedding_created_at",
]


def missing_required_properties(label: str, properties: set[str]) -> list[str]:
    required = NODE_PROPERTY_CONTRACTS[label]
    return [name for name in required if name not in properties]


def missing_common_provenance(properties: set[str]) -> list[str]:
    required = {"id", "source_dataset_id", "source_file_id", "source_record_id", "build_id"}
    return [name for name in sorted(required) if name not in properties]
