# AIHub 뷰티 데이터 AuraDB 그래프 구축

AIHub 뷰티 관련 데이터셋을 Neo4j AuraDB에 그래프 형태로 구축하기 위한 DB-only 파이프라인입니다.  
본 레포지토리는 원본 데이터를 직접 포함하지 않고, 원본 zip 파일을 로컬에서 스트리밍 처리하여 AuraDB에 적재하는 코드와 문서를 제공합니다.

## 구축 목적

이 프로젝트의 목적은 온라인 서비스나 질의응답 시스템을 바로 구현하는 것이 아니라, 향후 추천 시스템, CAG/RAG, 이미지 유사도 검색 등에 활용할 수 있는 그래프 데이터베이스 기반을 먼저 구축하는 것입니다.

현재 구축된 그래프는 다음 정보를 표현합니다.

- AIHub 데이터셋 단위 정보
- 원본 zip 내부 파일 단위 출처 정보
- JSON/JSONL/CSV에서 추출한 텍스트 문서
- 검색 및 RAG 확장을 위한 텍스트 chunk
- 이미지 파일 메타데이터
- 데이터셋, 원본 파일, 문서, chunk, 이미지 간 provenance 관계

## 사용 데이터

사용한 AIHub 데이터셋은 다음 2종입니다.

```text
71961: 문제성 피부 메이크업 추천 데이터
71886: 스킨케어 성분-효능 추천 데이터
```

원본 데이터는 로컬 작업 폴더의 `aihub/` 아래에 배치하여 처리했습니다. 원본 zip 파일은 레포지토리에 포함하지 않습니다.

## 처리 방식

전체 원본 zip 파일을 모두 압축 해제하지 않고, zip 내부 entry를 직접 읽어 처리했습니다.

처리 흐름은 다음과 같습니다.

```text
AIHub 원본 zip
  -> zip entry 스캔
  -> SourceFile manifest 생성
  -> 텍스트 record canonicalize
  -> JSONL batch 생성
  -> AuraDB batch 적재
  -> Image 메타데이터 노드 생성
  -> provenance 검증
```

이 방식은 원본 데이터를 중복 저장하지 않고, 파일 단위 출처를 유지하며, batch 단위로 품질 검증과 재적재를 수행할 수 있다는 장점이 있습니다.

## 현재 AuraDB 구축 결과

전체 zip build 기준:

```text
build_id: full-zip-20260627
SourceFile: 45,409
Document: 12,122
Chunk: 12,122
Image: 9,000
```

현재 AuraDB 전체 카운트는 앞서 수행한 pilot build 100건을 포함합니다.

```text
Dataset: 2
SourceFile: 45,509
Document: 12,222
Chunk: 12,222
Image: 9,000
QA: 0
```

검증 결과:

```text
OrphanChunk: 0
MissingProvenance: 0
OrphanImage: 0
```

## 그래프 구조

주요 노드 label은 다음과 같습니다.

```text
Dataset
SourceFile
Document
Chunk
Image
```

주요 관계는 다음과 같습니다.

```cypher
(source:SourceFile)-[:FROM_DATASET]->(dataset:Dataset)
(doc:Document)-[:FROM_FILE]->(source:SourceFile)
(chunk:Chunk)-[:PART_OF]->(doc:Document)
(img:Image)-[:FROM_FILE]->(source:SourceFile)
```

이미지 원본 바이너리는 AuraDB에 직접 저장하지 않았습니다. AuraDB에는 `Image` 노드로 `path`, `sha256`, `size_bytes`, `file_type`, `source_dataset_id`, `source_file_id` 등의 메타데이터와 관계만 저장합니다. 실제 이미지 원본은 로컬의 AIHub zip 파일 안에 유지됩니다.

## 주요 문서

- `docs/auradb_graph_structure_ko.md`: 한글 구축 과정 및 그래프 구조 설명
- `docs/auradb_graph_structure.md`: 기술 중심 그래프 구조 설명
- `docs/db_build.md`: CLI 실행 흐름
- `docs/db_handoff.md`: 구축 결과와 후속 작업 정리
- `data_inventory.md`: 데이터 인벤토리 정리

## 주요 CLI

로컬 개발 설치:

```powershell
python -m pip install -e .
```

테스트:

```powershell
$env:PYTHONPATH='src'
python -m unittest discover -s tests
```

zip 파일 스캔:

```powershell
python -m aihub_auradb.cli scan-zip --root aihub --output reports/aihub_zip_scan.json
```

zip 스트리밍 canonicalize:

```powershell
python -m aihub_auradb.cli zip-canonicalize `
  --root aihub `
  --output-dir data/processed/zip_full `
  --batch-size 1000
```

AuraDB schema 적용:

```powershell
python -m aihub_auradb.cli auradb-schema --env .env
```

AuraDB batch 적재:

```powershell
python -m aihub_auradb.cli auradb-load-batch-dir `
  --env .env `
  --manifest data/processed/zip_full/manifest_full.jsonl `
  --records-dir data/processed/zip_full/records `
  --build-id full-zip-20260627
```

이미지 노드 적재:

```powershell
python -m aihub_auradb.cli auradb-load-images `
  --env .env `
  --manifest data/processed/zip_full/manifest_full.jsonl `
  --build-id full-zip-20260627
```

AuraDB 검증:

```powershell
python -m aihub_auradb.cli auradb-verify --env .env --output reports/auradb_verify_with_images.json
```

로컬 Python TLS 체인 문제로 `CERTIFICATE_VERIFY_FAILED`가 발생하는 환경에서는 위 AuraDB 명령에 `--allow-self-signed-cert`를 추가해 재시도할 수 있습니다.

## Neo4j Browser 확인 쿼리

전체 노드 수:

```cypher
MATCH (n)
RETURN labels(n) AS labels, count(n) AS count
ORDER BY count DESC;
```

full build만 확인:

```cypher
MATCH (n)
WHERE n.build_id = 'full-zip-20260627'
RETURN labels(n) AS labels, count(n) AS count
ORDER BY count DESC;
```

텍스트 그래프 보기:

```cypher
MATCH p=(dataset:Dataset)<-[:FROM_DATASET]-(source:SourceFile)<-[:FROM_FILE]-(doc:Document)<-[:PART_OF]-(chunk:Chunk)
WHERE doc.build_id = 'full-zip-20260627'
RETURN p
LIMIT 50;
```

이미지 그래프 보기:

```cypher
MATCH p=(dataset:Dataset)<-[:FROM_DATASET]-(source:SourceFile)<-[:FROM_FILE]-(img:Image)
WHERE img.build_id = 'full-zip-20260627'
RETURN p
LIMIT 50;
```

무결성 확인:

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

## 보안 및 데이터 관리

이 레포지토리에는 다음 항목을 커밋하지 않습니다.

- `.env`
- AuraDB 인증 정보
- AIHub 원본 zip 데이터
- 추출/생성된 대용량 처리 산출물
- `reports/` 아래의 로컬 실행 리포트

`.gitignore`에서 위 항목을 제외하도록 설정했습니다.

## 향후 진행 가능 사항

다음 단계로는 아래 작업을 진행할 수 있습니다.

1. `Image.path`를 `zip_path`와 `entry_path`로 분리
2. 한국어 CSV/JSON 필드명 인코딩 및 컬럼 매핑 개선
3. 이미지 embedding 생성 및 유사 이미지 검색 구조 추가
4. 피부 고민, 성분, 효능, 추천 관계 추출
5. 서비스용 CAG/RAG 조회 API 설계
