# AIHub 뷰티 데이터 AuraDB 그래프 구축 정리

## 1. 구축 목적

본 문서는 AIHub 뷰티 관련 데이터셋을 Neo4j AuraDB에 그래프 형태로 구축한 과정과 현재 데이터베이스 구조를 정리한 문서입니다.

이번 작업의 목적은 온라인 서비스나 질의응답 시스템을 바로 만드는 것이 아니라, 향후 CAG/RAG 또는 추천 서비스에서 활용할 수 있는 데이터베이스 기반을 먼저 구축하는 것입니다.

현재 구축 범위는 다음과 같습니다.

- 원본 AIHub zip 파일 전체 확인
- zip 파일을 전부 압축 해제하지 않고 직접 스트리밍 처리
- 원본 파일 단위의 출처 정보 저장
- 텍스트 데이터의 `Document` / `Chunk` 노드 생성
- 이미지 파일의 `Image` 메타데이터 노드 생성
- AuraDB 적재 후 무결성 검증

현재 구축 범위에 포함하지 않은 항목은 다음과 같습니다.

- 온라인 API 서비스
- CAG 캐시 응답 시스템
- GraphRAG 답변 생성 시스템
- LLM 기반 답변 생성
- 이미지 원본 바이너리의 DB 직접 저장

## 2. 사용 데이터

원본 데이터는 다음 경로에 배치했습니다.

```text
aihub/
```

사용한 데이터셋은 AIHub 뷰티 관련 데이터 2종입니다.

```text
71961: 문제성 피부 메이크업 추천 데이터
71886: 스킨케어 성분-효능 추천 데이터
```

로컬 환경에서는 일부 한글 폴더명이 PowerShell 출력에서 깨져 보일 수 있으나, Python 코드에서는 정상적으로 접근하여 처리했습니다.

## 3. 전체 처리 방식

처음에는 압축을 모두 해제한 뒤 처리하는 방식도 고려했지만, 원본 데이터 용량이 크기 때문에 최종적으로는 zip 파일을 그대로 읽는 방식을 사용했습니다.

즉, 처리 방식은 다음과 같습니다.

```text
원본 zip 파일
  -> zip 내부 파일을 스트리밍으로 읽기
  -> SourceFile manifest 생성
  -> 텍스트 record canonicalize
  -> JSONL batch 생성
  -> AuraDB에 batch 단위 적재
```

이 방식의 장점은 다음과 같습니다.

- 원본 zip 파일을 중복으로 풀어 저장하지 않아도 됨
- 파일 단위 출처를 유지할 수 있음
- batch 단위로 중간 산출물과 품질 검증이 가능함
- AuraDB Free 환경에서도 점진적으로 적재 가능함

## 4. 구축 과정

### 4.1 원본 zip 파일 스캔

먼저 `aihub/` 폴더 아래의 zip 파일을 모두 스캔했습니다.

스캔 결과는 다음과 같습니다.

```text
zip 파일 수: 81개
zip 내부 전체 파일 entry 수: 45,409개
```

스캔 결과 파일:

```text
reports/aihub_zip_scan.json
```

이 단계에서는 실제 데이터를 DB에 넣지 않고, 로컬에 원본 파일이 모두 존재하는지와 내부 파일 구성을 확인했습니다.

### 4.2 실제 데이터 샘플 검증

전체 데이터를 바로 넣기 전에 실제 zip 파일에서 일부 샘플을 추출하여 파서가 정상 동작하는지 확인했습니다.

샘플 구성은 다음과 같습니다.

```text
71961: JSON 파일 50개
71886: CSV 파일 50개
```

샘플 경로:

```text
data/raw/aihub_71961_sample_real/
data/raw/aihub_71886_sample_real/
```

샘플 품질 검증 결과:

```text
71961: 50 records, quarantine 0
71886: 50 records, quarantine 0
```

관련 리포트:

```text
reports/quality_71961_real_sample.json
reports/quality_71886_real_sample.json
```

### 4.3 AuraDB 샘플 적재

샘플 데이터 100건을 먼저 AuraDB에 적재했습니다.

샘플 build ID:

```text
pilot-real-sample-20260627
```

샘플 적재 결과:

```text
Dataset: 2
SourceFile: 100
Document: 100
Chunk: 100
QA: 0
```

이 단계에서 확인한 내용은 다음과 같습니다.

- AuraDB 접속 정보가 정상인지
- schema constraint가 적용되는지
- canonical record가 그래프 구조로 적재되는지
- `Chunk -> Document -> SourceFile -> Dataset` 출처 관계가 유지되는지

검증 결과:

```text
OrphanChunk: 0
MissingProvenance: 0
```

### 4.4 전체 zip 스트리밍 처리

샘플 검증 후 전체 zip 파일을 직접 스트리밍하여 처리했습니다.

사용한 명령 형태:

```powershell
$env:PYTHONPATH='src'
python -m aihub_auradb.cli zip-canonicalize `
  --root aihub `
  --output-dir data/processed/zip_full `
  --batch-size 1000
```

생성된 주요 산출물:

```text
data/processed/zip_full/manifest_full.jsonl
data/processed/zip_full/records/
data/processed/zip_full/quarantine_full.jsonl
data/processed/zip_full/quality_full.json
```

전체 canonicalization 결과:

```text
zip 파일 수: 81
전체 SourceFile entry 수: 45,409
텍스트 canonical record 수: 12,122
record batch 수: 13
quarantine 수: 18,031
duplicate id 수: 0
missing provenance record 수: 0
quality passed: true
```

여기서 `quarantine`은 텍스트 record로 변환할 수 없는 항목을 의미합니다. 이 항목들은 `Document`나 `Chunk`로 만들지는 않았지만, 원본 파일 자체는 `SourceFile`로 추적할 수 있게 유지했습니다.

### 4.5 전체 데이터 AuraDB 적재

전체 데이터는 다음 build ID로 적재했습니다.

```text
full-zip-20260627
```

적재 방식은 다음과 같습니다.

```text
1. Dataset 노드 생성
2. SourceFile 노드 생성
3. SourceFile -> Dataset 관계 생성
4. Document 노드 생성
5. Chunk 노드 생성
6. Document -> SourceFile 관계 생성
7. Chunk -> Document 관계 생성
```

전체 build 적재 결과:

```text
SourceFile: 45,409
Document: 12,122
Chunk: 12,122
```

데이터셋별 Document 수:

```text
71886: 9,000 documents
71961: 3,122 documents
```

### 4.6 이미지 노드 추가

처음에는 이미지를 `SourceFile`로만 관리했지만, 이후 이미지 파일을 그래프에서 명확히 볼 수 있도록 `Image` 노드를 추가했습니다.

중요한 점은 이미지 원본 바이너리를 AuraDB에 직접 저장하지 않았다는 것입니다.

현재 구조는 다음과 같습니다.

```text
이미지 원본 파일: 기존 zip 내부에 유지
AuraDB: Image 노드에 path, sha256, size_bytes, file_type 등 메타데이터 저장
```

이미지 노드 적재 결과:

```text
Image: 9,000
Image -> SourceFile 연결: 9,000
orphan Image: 0
```

현재 `Image` 노드는 모두 `71886` 데이터셋에서 생성되었습니다.

## 5. 현재 AuraDB 그래프 구조

현재 AuraDB에는 다음 주요 노드가 있습니다.

```text
Dataset
SourceFile
Document
Chunk
Image
```

### 5.1 Dataset

AIHub 데이터셋 하나를 의미합니다.

주요 속성:

```text
id
name
aihub_dataset_sn
source_url
manifest_version
build_id
```

현재 데이터셋:

```text
71886
71961
```

### 5.2 SourceFile

원본 zip 내부의 개별 파일 entry를 의미합니다.

주요 속성:

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

`path`에는 zip 파일 경로와 zip 내부 파일 경로가 포함되어 있어, 원본 파일을 추적할 수 있습니다.

### 5.3 Document

JSON, JSONL, CSV에서 추출한 하나의 정규화된 텍스트 record를 의미합니다.

주요 속성:

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

### 5.4 Chunk

검색과 향후 RAG 처리를 위한 텍스트 단위입니다.

현재는 하나의 canonical record를 하나의 chunk로 저장했습니다.

```text
chunking_method = record_as_chunk
```

주요 속성:

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
build_id
```

### 5.5 Image

원본 zip 내부 이미지 파일을 나타내는 노드입니다.

주요 속성:

```text
id
path
sha256
size_bytes
file_type
source_dataset_id
source_file_id
build_id
```

이미지 원본 자체는 DB에 저장하지 않았고, 원본 zip 파일 안에 유지했습니다.

## 6. 관계 구조

현재 주요 관계는 다음과 같습니다.

### 6.1 SourceFile -> Dataset

```cypher
(source:SourceFile)-[:FROM_DATASET]->(dataset:Dataset)
```

각 원본 파일이 어떤 AIHub 데이터셋에서 왔는지 나타냅니다.

### 6.2 Document -> SourceFile

```cypher
(doc:Document)-[:FROM_FILE]->(source:SourceFile)
```

각 텍스트 record가 어떤 원본 파일에서 추출되었는지 나타냅니다.

### 6.3 Chunk -> Document

```cypher
(chunk:Chunk)-[:PART_OF]->(doc:Document)
```

각 chunk가 어떤 document에 속하는지 나타냅니다.

### 6.4 Image -> SourceFile

```cypher
(img:Image)-[:FROM_FILE]->(source:SourceFile)
```

각 이미지 노드가 어떤 원본 파일 entry에 대응되는지 나타냅니다.

## 7. 최종 적재 결과

현재 AuraDB 전체 카운트는 다음과 같습니다.

```text
Dataset: 2
SourceFile: 45,509
Document: 12,222
Chunk: 12,222
Image: 9,000
QA: 0
```

단, 위 수치는 샘플 pilot build 100건이 포함된 전체 카운트입니다.

전체 zip build만 보면 다음과 같습니다.

```text
build_id: full-zip-20260627
SourceFile: 45,409
Document: 12,122
Chunk: 12,122
Image: 9,000
```

## 8. 검증 결과

최종 검증 결과는 다음과 같습니다.

```text
OrphanChunk: 0
MissingProvenance: 0
OrphanImage: 0
```

이는 다음을 의미합니다.

- 모든 `Chunk`는 `Document`에 연결되어 있음
- 모든 주요 노드는 원본 dataset/file 출처 정보를 가지고 있음
- 모든 `Image`는 `SourceFile`에 연결되어 있음

관련 검증 리포트:

```text
reports/auradb_verify_after_full_load_process.json
reports/auradb_verify_with_images.json
reports/auradb_image_verify.json
reports/auradb_build_breakdown_full.json
```

## 9. Neo4j Browser 확인 쿼리

### 9.1 전체 노드 수 확인

```cypher
MATCH (n)
RETURN labels(n) AS labels, count(n) AS count
ORDER BY count DESC;
```

### 9.2 full build만 확인

```cypher
MATCH (n)
WHERE n.build_id = 'full-zip-20260627'
RETURN labels(n) AS labels, count(n) AS count
ORDER BY count DESC;
```

### 9.3 데이터셋별 문서 수

```cypher
MATCH (d:Document)
WHERE d.build_id = 'full-zip-20260627'
RETURN d.source_dataset_id AS dataset_id, count(d) AS documents
ORDER BY dataset_id;
```

### 9.4 텍스트 그래프 보기

```cypher
MATCH p=(dataset:Dataset)<-[:FROM_DATASET]-(source:SourceFile)<-[:FROM_FILE]-(doc:Document)<-[:PART_OF]-(chunk:Chunk)
WHERE doc.build_id = 'full-zip-20260627'
RETURN p
LIMIT 50;
```

### 9.5 이미지 그래프 보기

```cypher
MATCH p=(dataset:Dataset)<-[:FROM_DATASET]-(source:SourceFile)<-[:FROM_FILE]-(img:Image)
WHERE img.build_id = 'full-zip-20260627'
RETURN p
LIMIT 50;
```

### 9.6 이미지 메타데이터 확인

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

### 9.7 텍스트 내용 확인

```cypher
MATCH (doc:Document)<-[:PART_OF]-(chunk:Chunk)
WHERE doc.build_id = 'full-zip-20260627'
RETURN doc.source_dataset_id AS dataset_id,
       doc.title AS title,
       chunk.text AS text
LIMIT 20;
```

### 9.8 무결성 확인

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

## 10. 이미지 원본을 DB에 직접 넣지 않은 이유

Neo4j/AuraDB에 이미지 파일 자체를 base64 문자열 등으로 저장하는 것은 기술적으로 가능합니다.

하지만 본 프로젝트에서는 다음 이유로 이미지 원본을 DB에 직접 넣지 않았습니다.

- AuraDB 용량을 빠르게 소모함
- 그래프 탐색 성능에 불리함
- Neo4j Browser에서 이미지 원본을 직접 미리보기하는 장점이 크지 않음
- 이미지 파일은 파일 스토리지 또는 zip 원본에 두는 편이 관리에 적합함
- 그래프 DB에는 이미지와 다른 노드 간의 관계 및 메타데이터를 저장하는 것이 더 적절함

따라서 현재 설계는 다음과 같습니다.

```text
이미지 원본: 기존 zip 파일 내부
AuraDB: Image 메타데이터 노드와 관계
```

향후 이미지 기반 유사도 검색이 필요하다면, 이미지 원본을 DB에 넣는 대신 CLIP 등으로 embedding을 추출하여 `Image.embedding` 속성과 vector index를 추가하는 방식이 더 적절합니다.

## 11. 향후 진행 가능 사항

다음 단계로 진행할 수 있는 작업은 다음과 같습니다.

1. pilot build 삭제 또는 `build_id` 필터 사용 방식 결정
2. `Image.path`를 `zip_path`와 `entry_path`로 분리
3. 한국어 CSV/JSON 필드명 인코딩 및 컬럼 매핑 개선
4. 이미지 embedding 생성 및 유사 이미지 검색 구조 추가
5. 피부 고민, 성분, 효능, 추천 관계 추출
6. 추후 서비스용 CAG/RAG 조회 API 설계

현재 단계에서는 DB 구축과 검증까지 완료된 상태이며, 이후 서비스 또는 추천 로직 개발을 위한 기반 데이터베이스로 활용할 수 있습니다.
