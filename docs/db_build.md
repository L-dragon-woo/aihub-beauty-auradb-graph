# AuraDB Knowledge DB Build

This project implements the DB-only foundation from `.omx/plans/auradb-graphrag-aihub-plan.md`.

Current scope:

- Generate raw file manifests.
- Profile staged AIHub-like JSON files.
- Canonicalize records with deterministic IDs and provenance.
- Quarantine malformed or unmappable records.
- Generate AuraDB constraints, full-text indexes, optional vector index Cypher.
- Apply the AuraDB schema from `.env` credentials.
- Load validated canonical real-sample records into AuraDB.
- Verify graph counts and source provenance after load.
- Generate future CAG/GraphRAG readiness query examples.
- Run local tests without requiring AuraDB credentials.

Out of scope:

- Online service/API.
- CAG cache serving.
- GraphRAG answer endpoint.
- LLM answer generation.
- Raw image analysis.

## Local Verification

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests
```

## Example Artifact Generation

```powershell
$env:PYTHONPATH='src'
python -m aihub_auradb.cli manifest --dataset-root tests/fixtures/aihub_71961 --dataset-id 71961 --output reports/manifest_71961.jsonl
python -m aihub_auradb.cli profile --dataset-root tests/fixtures/aihub_71961 --output reports/profile_71961.json
python -m aihub_auradb.cli canonicalize --dataset-root tests/fixtures/aihub_71961 --dataset-id 71961 --records-output data/processed/records_71961.jsonl --quarantine-output reports/quarantine_71961.jsonl --quality-output reports/quality_71961.json
python -m aihub_auradb.cli schema --output reports/auradb_schema.cypher
python -m aihub_auradb.cli readiness --output reports/readiness_queries
```

Add `--include-vector` to the schema command only after chunking and embedding provenance are stable.

For both fixture datasets, run:

```powershell
$env:PYTHONPATH='src'
python -m aihub_auradb.cli manifest --dataset-root tests/fixtures/aihub_71886 --dataset-id 71886 --output reports/manifest_71886.jsonl
python -m aihub_auradb.cli profile --dataset-root tests/fixtures/aihub_71886 --output reports/profile_71886.json
python -m aihub_auradb.cli canonicalize --dataset-root tests/fixtures/aihub_71886 --dataset-id 71886 --records-output data/processed/records_71886.jsonl --quarantine-output reports/quarantine_71886.jsonl --quality-output reports/quality_71886.json
```

## Real Data Handoff

The original AIHub zip files are staged under:

- `aihub/02.문제성 피부 메이크업 추천 데이터/`
- `aihub/03.스킨케어 성분-효능 추천 데이터/`

The real-data pilot uses extracted samples from those zip files:

- `data/raw/aihub_71961_sample_real/`
- `data/raw/aihub_71886_sample_real/`

Pilot quality reports:

- `reports/quality_71961_real_sample.json`: 50 records, 0 quarantine.
- `reports/quality_71886_real_sample.json`: 50 records, 0 quarantine.

## AuraDB Pilot Load

Keep credentials in `.env`:

- `NEO4J_URI`
- `NEO4J_USERNAME`
- `NEO4J_PASSWORD`
- `NEO4J_DATABASE`

For the current AuraDB Free instance, the working database name was `161aa5e9`. If `.env` still has `NEO4J_DATABASE=neo4j`, override it for the command:

```powershell
$env:PYTHONPATH='src'
$env:NEO4J_DATABASE='161aa5e9'
```

Apply schema:

```powershell
python -m aihub_auradb.cli auradb-schema --env .env
```

Load the real sample:

```powershell
python -m aihub_auradb.cli auradb-load --env .env `
  --manifest reports/manifest_71961_real_sample.jsonl `
  --manifest reports/manifest_71886_real_sample.jsonl `
  --records data/processed/records_71961_real_sample.jsonl `
  --records data/processed/records_71886_real_sample.jsonl `
  --build-id pilot-real-sample-20260627
```

Verify counts and provenance:

```powershell
python -m aihub_auradb.cli auradb-verify --env .env --output reports/auradb_verify_real_sample.json
```

Latest pilot evidence:

- Schema: 21 statements applied to AuraDB database `161aa5e9`.
- Load summary: 2 datasets, 100 source files, 100 documents, 100 chunks, 0 QA.
- Verification: `OrphanChunk = 0`, `MissingProvenance = 0`.

If the local Python TLS chain fails with `CERTIFICATE_VERIFY_FAILED`, retry the same command with `--allow-self-signed-cert`. That flag converts `neo4j+s://` to `neo4j+ssc://` for the explicit command only.

Before expanding to the full original data, keep the same sequence: sample/profile/canonicalize, review quarantine, then batch-load with clear limits.

See also `docs/db_handoff.md`.
