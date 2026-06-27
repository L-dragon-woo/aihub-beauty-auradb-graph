# AIHub Beauty AuraDB Graph Build

AIHub 뷰티 관련 데이터셋을 Neo4j AuraDB에 그래프 형태로 구축하기 위한 DB-only 파이프라인입니다.

## 현재 범위

- AIHub 원본 zip 파일 스캔
- zip 압축 전체 해제 없이 스트리밍 처리
- `SourceFile`, `Document`, `Chunk`, `Image` 그래프 노드 구성
- AuraDB schema 적용 및 batch 적재
- provenance 무결성 검증
- 교수님 공유용 한글 구축 문서 제공

## 주요 문서

- `docs/auradb_graph_structure_ko.md`: 한글 구축 과정 및 그래프 구조 설명
- `docs/auradb_graph_structure.md`: 영문/기술 중심 구조 설명
- `docs/db_build.md`: CLI 실행 흐름
- `docs/db_handoff.md`: 구축 결과와 후속 작업 정리

## 보안 및 데이터 정책

이 레포에는 다음 항목을 커밋하지 않습니다.

- `.env`
- AIHub 원본 zip 데이터
- 추출/생성된 대용량 처리 산출물
- AuraDB 인증 정보

원본 데이터와 생성 산출물은 로컬 작업 폴더에서만 관리합니다.
