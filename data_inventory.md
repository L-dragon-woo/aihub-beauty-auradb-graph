# Data Inventory Template

Fill this file after staging the real AIHub downloads.

## Dataset 71961

- Name: problematic-skin makeup recommendation data
- Staged path: `data/raw/aihub_71961/`
- Source URL: https://aihub.or.kr/aihubdata/data/view.do?aihubDataSe=data&dataSetSn=71961
- Local manifest: `reports/manifest_71961.jsonl`
- Profile report: `reports/profile_71961.json`
- Canonical records: `data/processed/records_71961.jsonl`
- Quarantine report: `reports/quarantine_71961.jsonl`
- Quality report: `reports/quality_71961.json`
- Access/license notes: Pending real data review
- Version/build notes: Pending real data review
- Usable fields: Pending schema profiling
- Ignored fields: Pending schema profiling
- Known gaps: Pending schema profiling

## Dataset 71886

- Name: skincare ingredient-effect recommendation data
- Staged path: `data/raw/aihub_71886/`
- Source URL: https://aihub.or.kr/aihubdata/data/view.do?aihubDataSe=data&dataSetSn=71886
- Local manifest: `reports/manifest_71886.jsonl`
- Profile report: `reports/profile_71886.json`
- Canonical records: `data/processed/records_71886.jsonl`
- Quarantine report: `reports/quarantine_71886.jsonl`
- Quality report: `reports/quality_71886.json`
- Access/license notes: Pending real data review
- Version/build notes: Pending real data review
- Usable fields: Pending schema profiling
- Ignored fields: Pending schema profiling
- Known gaps: Pending schema profiling

## Completion Checklist

- [ ] Manifest exists for both datasets.
- [ ] File hashes are recorded.
- [ ] Representative records are profiled.
- [ ] In-scope fields are chosen.
- [ ] Quarantine reasons are reviewed.
- [ ] AuraDB schema Cypher is reviewed before mutation.
- [ ] Pilot load scope is documented.
