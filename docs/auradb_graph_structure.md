# AuraDB Graph Structure

This document describes how the AIHub beauty datasets are represented in AuraDB.

## Scope

The current database is a DB-only foundation. It stores source provenance, text records, text chunks, and image file metadata. It does not store image binary bytes, run an online service, answer with CAG/RAG, or perform LLM generation.

## Source Data

Original data location:

```text
aihub/
```

The zip archives were not fully extracted. The full build streamed the 81 zip files directly and wrote intermediate JSONL artifacts.

Key local artifacts:

```text
data/processed/zip_full/manifest_full.jsonl
data/processed/zip_full/records/
data/processed/zip_full/quality_full.json
reports/auradb_verify_after_full_load_process.json
reports/auradb_verify_with_images.json
reports/auradb_image_verify.json
reports/auradb_build_breakdown_full.json
```

## Builds

Two build IDs currently exist in AuraDB:

```text
pilot-real-sample-20260627
full-zip-20260627
```

The pilot build was the first 100-record validation load. The full build is the zip-streamed dataset build.

When querying the completed dataset, prefer:

```cypher
WHERE n.build_id = 'full-zip-20260627'
```

or the equivalent label-specific property filter.

## Build Process

This section describes the actual process used to construct the current AuraDB graph.

### 1. Raw Data Placement

The AIHub files were placed under:

```text
aihub/
```

The two relevant dataset folders are:

```text
aihub/02...
aihub/03...
```

The folder names may appear garbled in some PowerShell output because of Korean filename encoding display, but the files are accessible from Python and PowerShell.

### 2. Zip Inventory

The first step was to scan the zip files without extracting them.

Result:

```text
Zip files: 81
Total source entries: 45,409
```

The scan result was written to:

```text
reports/aihub_zip_scan.json
```

This step answered whether the local machine had the original AIHub files available.

### 3. Real Sample Pilot

Before processing everything, a small real-data sample was extracted from the original zip files.

Sample folders:

```text
data/raw/aihub_71961_sample_real/
data/raw/aihub_71886_sample_real/
```

Sample size:

```text
71961: 50 JSON files
71886: 50 CSV files
```

The sample was canonicalized first to prove that the parser could read the real schemas.

Sample quality reports:

```text
reports/quality_71961_real_sample.json
reports/quality_71886_real_sample.json
```

Both sample quality reports passed with zero quarantine.

### 4. AuraDB Pilot Load

The sample records were loaded into AuraDB first.

Build ID:

```text
pilot-real-sample-20260627
```

Pilot result:

```text
Dataset: 2
SourceFile: 100
Document: 100
Chunk: 100
QA: 0
```

This pilot confirmed:

```text
AuraDB credentials work
Schema constraints can be applied
Canonical records can be loaded
Chunk/document provenance is valid
```

The local Python TLS chain rejected the Aura certificate path with `CERTIFICATE_VERIFY_FAILED`, so the explicit `--allow-self-signed-cert` command option was added. The default remains strict TLS.

### 5. Full Zip Streaming Canonicalization

After the pilot succeeded, the full dataset was processed directly from the original zip files.

The key design decision was:

```text
Do not extract all zip files to data/raw/.
Stream each zip entry and write structured JSONL batches.
```

This avoided duplicating several gigabytes of raw files on disk.

Command shape:

```powershell
$env:PYTHONPATH='src'
python -m aihub_auradb.cli zip-canonicalize `
  --root aihub `
  --output-dir data/processed/zip_full `
  --batch-size 1000
```

Generated outputs:

```text
data/processed/zip_full/manifest_full.jsonl
data/processed/zip_full/records/records_000001.jsonl
...
data/processed/zip_full/records/records_000013.jsonl
data/processed/zip_full/quarantine_full.jsonl
data/processed/zip_full/quality_full.json
```

Full canonicalization result:

```text
Zip files: 81
Source file entries: 45,409
Canonical text records: 12,122
Record batches: 13
Quarantine: 18,031
Duplicate IDs: 0
Missing provenance records: 0
Quality passed: true
```

The quarantine count means those entries did not produce usable text for `Document` or `Chunk`. They were not silently ignored: they were written to `quarantine_full.jsonl`.

### 6. Full AuraDB Load

The full build was loaded with:

```text
build_id = full-zip-20260627
```

The loader first merged `Dataset` and `SourceFile` nodes, then loaded each canonical record batch into `Document` and `Chunk`.

Important behavior:

```text
SourceFile nodes represent every file entry from the original zip files.
Document/Chunk nodes represent only canonical text records.
Image nodes represent image file entries.
```

The full text load produced:

```text
SourceFile: 45,409
Document: 12,122
Chunk: 12,122
```

The initial process was interrupted once, but the loader uses `MERGE`, so reruns are idempotent for the same IDs. After the process finished, AuraDB verification showed no provenance errors.

### 7. Image Node Load

After the text graph was complete, image entries were added as `Image` nodes.

Important distinction:

```text
The actual image bytes were not inserted into AuraDB.
AuraDB stores image metadata and source linkage.
The original image bytes remain inside the zip archives.
```

Image source type:

```text
jpg
```

Image load result:

```text
Image: 9,000
linked Image -> SourceFile: 9,000
orphan Image: 0
```

All current image nodes are from dataset `71886`.

### 8. Final Verification

Final verification checked:

```text
Label counts
Chunk -> Document relationships
Image -> SourceFile relationships
Missing provenance properties
Dataset splits
Build ID splits
```

Final total counts, including the earlier pilot build:

```text
Dataset: 2
SourceFile: 45,509
Document: 12,222
Chunk: 12,222
Image: 9,000
QA: 0
```

The full build only has:

```text
SourceFile: 45,409
Document: 12,122
Chunk: 12,122
Image: 9,000
```

Final verification files:

```text
reports/auradb_verify_after_full_load_process.json
reports/auradb_verify_with_images.json
reports/auradb_image_verify.json
reports/auradb_build_breakdown_full.json
```

## Node Labels

### Dataset

Represents an AIHub dataset.

Important properties:

```text
id
name
aihub_dataset_sn
source_url
manifest_version
build_id
```

Current dataset IDs:

```text
71886
71961
```

### SourceFile

Represents a file entry from the original AIHub zip archives.

Important properties:

```text
id
path
sha256
size_bytes
file_type
source_dataset_id
manifest_version
build_id
```

`path` points to the zip path and internal entry path. This is the canonical pointer back to the original file.

### Document

Represents a canonical text record parsed from JSON, JSONL, or CSV.

Important properties:

```text
id
document_type
title
raw_id
language
source_dataset_id
source_file_id
source_record_id
content_hash
extraction_method
confidence
build_id
```

Current full build document split:

```text
71886: 9,000 documents
71961: 3,122 documents
```

### Chunk

Represents the searchable text chunk for a `Document`.

Important properties:

```text
id
text
chunk_index
token_count
chunking_method
source_document_id
source_dataset_id
source_file_id
source_record_id
content_hash
extraction_method
confidence
build_id
```

Current implementation uses one chunk per canonical record:

```text
chunking_method = record_as_chunk
```

### Image

Represents an original image file entry from the zip archives.

Important properties:

```text
id
path
sha256
size_bytes
file_type
source_dataset_id
source_file_id
build_id
extraction_method
confidence
```

The image binary bytes are not stored in AuraDB. The original image remains inside the zip file; AuraDB stores the metadata and source pointer.

Current image count:

```text
Image: 9,000
```

All current `Image` nodes come from dataset `71886`.

## Relationships

### SourceFile to Dataset

```cypher
(source:SourceFile)-[:FROM_DATASET]->(dataset:Dataset)
```

Every source file should point back to one dataset.

### Document to SourceFile

```cypher
(doc:Document)-[:FROM_FILE]->(source:SourceFile)
```

Every document should point back to its source file.

### Chunk to Document

```cypher
(chunk:Chunk)-[:PART_OF]->(doc:Document)
```

Every chunk should belong to one document.

### Image to SourceFile

```cypher
(img:Image)-[:FROM_FILE]->(source:SourceFile)
```

Every image should point back to its source file.

## Current Counts

Total database counts, including the earlier pilot build:

```text
Dataset: 2
SourceFile: 45,509
Document: 12,222
Chunk: 12,222
Image: 9,000
QA: 0
```

Full zip build only:

```text
Build ID: full-zip-20260627
SourceFile: 45,409
Document: 12,122
Chunk: 12,122
Image: 9,000
```

The 100-count difference in `SourceFile`, `Document`, and `Chunk` comes from the earlier pilot sample build.

## Quality Results

Full zip canonicalization:

```text
Zip files: 81
Source file entries: 45,409
Canonical text records: 12,122
Quarantine: 18,031
Duplicate IDs: 0
Missing provenance records: 0
Passed: true
```

The quarantine items are records/files that did not produce usable text. They were not loaded as `Document` or `Chunk`, but their source files remain represented through `SourceFile`.

AuraDB verification:

```text
OrphanChunk: 0
MissingProvenance: 0
Orphan Image: 0
```

## Neo4j Browser Queries

### Count All Labels

```cypher
MATCH (n)
RETURN labels(n) AS labels, count(n) AS count
ORDER BY count DESC;
```

### Count Full Build Only

```cypher
MATCH (n)
WHERE n.build_id = 'full-zip-20260627'
RETURN labels(n) AS labels, count(n) AS count
ORDER BY count DESC;
```

### Dataset to Text Records

```cypher
MATCH p=(dataset:Dataset)<-[:FROM_DATASET]-(source:SourceFile)<-[:FROM_FILE]-(doc:Document)<-[:PART_OF]-(chunk:Chunk)
WHERE doc.build_id = 'full-zip-20260627'
RETURN p
LIMIT 50;
```

### Dataset to Images

```cypher
MATCH p=(dataset:Dataset)<-[:FROM_DATASET]-(source:SourceFile)<-[:FROM_FILE]-(img:Image)
WHERE img.build_id = 'full-zip-20260627'
RETURN p
LIMIT 50;
```

### Image Metadata

```cypher
MATCH (img:Image)-[:FROM_FILE]->(source:SourceFile)
WHERE img.build_id = 'full-zip-20260627'
RETURN img.source_dataset_id AS dataset_id,
       img.path AS path,
       img.file_type AS file_type,
       img.size_bytes AS size_bytes,
       img.sha256 AS sha256
LIMIT 30;
```

### Text Content

```cypher
MATCH (doc:Document)<-[:PART_OF]-(chunk:Chunk)
WHERE doc.build_id = 'full-zip-20260627'
RETURN doc.source_dataset_id AS dataset_id,
       doc.title AS title,
       chunk.text AS text
LIMIT 20;
```

### Provenance Checks

```cypher
MATCH (c:Chunk)
WHERE NOT (c)-[:PART_OF]->(:Document)
RETURN count(c) AS orphanChunks;
```

```cypher
MATCH (img:Image)
WHERE NOT (img)-[:FROM_FILE]->(:SourceFile)
RETURN count(img) AS orphanImages;
```

```cypher
MATCH (n)
WHERE (n:Document OR n:Chunk OR n:QA OR n:Image)
  AND (n.source_dataset_id IS NULL OR n.source_file_id IS NULL)
RETURN count(n) AS missingProvenance;
```

## Why Images Are Metadata Nodes

AuraDB can technically store base64 image bytes as a property, but this is not the chosen design.

The current design keeps:

```text
Image binary: original zip archives
AuraDB: Image node metadata and graph relationships
```

This keeps AuraDB small enough to query, avoids storing large binary payloads in a graph database, and still allows the application to find the original image by `Image.path`.

If image similarity search is needed later, add image embeddings to `Image` nodes and create a vector index. The original image bytes still do not need to live inside AuraDB.

## Next Possible Steps

1. Decide whether to delete the pilot build or keep filtering by `build_id`.
2. Split `Image.path` into `zip_path` and `entry_path` for easier application-level image loading.
3. Improve Korean text decoding and CSV column mapping.
4. Add image embeddings for visual similarity search.
5. Extract domain relationships such as skin concern, ingredient, effect, and recommendation.
