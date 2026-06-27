# DB Handoff Notes

This handoff describes the current DB-build foundation and the completed AuraDB Free real-sample pilot.

## Implemented

- Python package: `src/aihub_auradb/`
- CLI entrypoint: `python -m aihub_auradb.cli`
- Raw manifest generation with SHA-256 hashes.
- JSON schema profiling.
- Canonical JSON record extraction for common QA/document shapes.
- Quarantine reporting for malformed or empty records.
- Deterministic ID helpers.
- Starter Korean taxonomy normalization.
- Machine-readable graph property contracts.
- AuraDB schema Cypher generation.
- AuraDB schema application command.
- AuraDB canonical-record load command.
- AuraDB count and provenance verification command.
- Future CAG and GraphRAG readiness query generation.
- Local fixtures and unit tests.

## Generated Local Artifacts

- `reports/manifest_71961.jsonl`
- `reports/manifest_71886.jsonl`
- `reports/profile_71961.json`
- `reports/profile_71886.json`
- `reports/quality_71961.json`
- `reports/quality_71886.json`
- `reports/quarantine_71961.jsonl`
- `reports/quarantine_71886.jsonl`
- `reports/auradb_schema.cypher`
- `reports/readiness_queries/`
- `data/processed/records_71961.jsonl`
- `data/processed/records_71886.jsonl`
- `reports/manifest_71961_real_sample.jsonl`
- `reports/manifest_71886_real_sample.jsonl`
- `reports/quality_71961_real_sample.json`
- `reports/quality_71886_real_sample.json`
- `data/processed/records_71961_real_sample.jsonl`
- `data/processed/records_71886_real_sample.jsonl`
- `reports/auradb_verify_real_sample.json`

## AuraDB Pilot Evidence

The real sample pilot has been loaded into AuraDB Free:

- Database: `161aa5e9`
- Schema application: 21 statements applied.
- Load summary: 2 datasets, 100 source files, 100 documents, 100 chunks, 0 QA.
- Verification report: `reports/auradb_verify_real_sample.json`
- Provenance checks: `OrphanChunk = 0`, `MissingProvenance = 0`

The local Python TLS chain rejected the Aura certificate path with `CERTIFICATE_VERIFY_FAILED`, so the successful pilot used the explicit `--allow-self-signed-cert` CLI flag. The default remains strict TLS verification.

## Full Zip Load Evidence

The original zip files were not fully extracted to `data/raw/`. Instead, the full dataset was streamed directly from the 81 zip files under `aihub/`.

Local full-zip canonicalization:

- Zip files scanned: 81
- Source file entries: 45,409
- Canonical text records: 12,122
- Record batches: 13
- Quality report: `data/processed/zip_full/quality_full.json`
- Batch records: `data/processed/zip_full/records/`
- Full manifest: `data/processed/zip_full/manifest_full.jsonl`

AuraDB full build:

- Build ID: `full-zip-20260627`
- SourceFile: 45,409
- Image: 9,000
- Document: 12,122
- Chunk: 12,122
- Dataset split:
  - 71886: 27,001 source files, 9,000 documents
  - 71961: 18,408 source files, 3,122 documents
- Verification report: `reports/auradb_verify_after_full_load_process.json`
- Build breakdown report: `reports/auradb_build_breakdown_full.json`
- Image verification report: `reports/auradb_image_verify.json`

The total database also still includes the earlier pilot sample build (`pilot-real-sample-20260627`), so total Document/Chunk counts are 12,222 rather than 12,122.

Image nodes are metadata nodes for the original image files inside the zip archives. The image binaries remain in the original zip files; AuraDB stores the zip entry path, hash, size, file type, dataset id, and source file linkage.

## Next Implementation Slice

Before full-data loading:

1. Expand extraction from sample zip entries to batch extraction or streaming.
2. Run manifest/profile/canonicalize per dataset shard.
3. Review quarantine and quality reports for each shard.
4. Batch-load into AuraDB with a fixed `build_id` and verify counts after each batch.
5. Only after graph counts are stable, decide whether to add embeddings/vector indexes.

## Future Service Readiness

The DB foundation intentionally does not implement CAG or GraphRAG services. It prepares:

- source-grounded chunks and QA records,
- future cache-card source queries,
- future graph expansion queries,
- provenance and confidence contracts,
- quality gates before service consumption.
