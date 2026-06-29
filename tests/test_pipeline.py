from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aihub_auradb.canonical import canonicalize_manifest
from aihub_auradb.env import allow_self_signed_scheme
from aihub_auradb.extracted import canonicalize_extracted_tree, extract_zip_tree
from aihub_auradb.ids import stable_id
from aihub_auradb.manifest import build_manifest
from aihub_auradb.profile import profile_json_files
from aihub_auradb.quality import build_quality_report
from aihub_auradb.schema import READINESS_QUERIES, schema_cypher
from aihub_auradb.graph_loader import load_canonical_records, split_cypher
from aihub_auradb.contracts import NODE_PROPERTY_CONTRACTS, missing_common_provenance, missing_required_properties
from aihub_auradb.taxonomy import normalize_alias
from aihub_auradb.ziptools import sample_zip_entries, scan_zip
from aihub_auradb.zipbatch import canonicalize_zip_tree
import zipfile


FIXTURES = Path(__file__).parent / "fixtures"


class PipelineTests(unittest.TestCase):
    def test_stable_ids_are_deterministic(self) -> None:
        first = stable_id("Document", "71961", "sample.json", "record-1")
        second = stable_id("Document", "71961", "sample.json", "record-1")
        other = stable_id("Document", "71961", "sample.json", "record-2")
        self.assertEqual(first, second)
        self.assertNotEqual(first, other)

    def test_canonical_ids_do_not_change_for_ignored_field_changes(self) -> None:
        source_file_id = stable_id("SourceFile", "71961", "sample.json")
        first = stable_id("CanonicalRecord", source_file_id, "record-1", "qa")
        second = stable_id("CanonicalRecord", source_file_id, "record-1", "qa")
        self.assertEqual(first, second)

    def test_manifest_profiles_and_canonicalizes_fixture(self) -> None:
        root = FIXTURES / "aihub_71961"
        manifest = build_manifest(root, "71961", "test")
        self.assertEqual(len(manifest), 1)
        self.assertEqual(manifest[0].source_dataset_id, "71961")
        self.assertEqual(manifest[0].file_type, "json")

        profile = profile_json_files([root / manifest[0].path])
        self.assertEqual(profile["records_sampled"], 2)
        self.assertIn("question", profile["key_counts"])

        records, quarantine = canonicalize_manifest(root, manifest)
        self.assertEqual(len(records), 1)
        self.assertEqual(len(quarantine), 1)
        self.assertEqual(quarantine[0].reason_code, "empty_text")

        report = build_quality_report(records, quarantine)
        self.assertTrue(report.passed)
        self.assertEqual(report.quarantine_count, 1)
        self.assertEqual(report.failure_reasons["empty_text"], 1)
        self.assertEqual(report.record_type_counts["qa"], 1)

    def test_quality_fails_for_empty_or_all_quarantined_inputs(self) -> None:
        empty = build_quality_report([], [])
        self.assertFalse(empty.passed)

        root = FIXTURES / "aihub_71961"
        manifest = build_manifest(root, "71961", "test")
        records, quarantine = canonicalize_manifest(root, manifest)
        all_failed = build_quality_report([], quarantine)
        self.assertFalse(all_failed.passed)
        self.assertGreater(all_failed.quarantine_count, 0)

    def test_profile_reports_malformed_json_and_skips_non_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            malformed = root / "bad.json"
            ignored = root / "note.txt"
            malformed.write_text("{bad", encoding="utf-8")
            ignored.write_text("plain text", encoding="utf-8")
            profile = profile_json_files([malformed, ignored])
            self.assertEqual(profile["records_sampled"], 0)
            self.assertEqual(len(profile["failed_files"]), 1)
            self.assertEqual(profile["skipped_files"], 1)

    def test_utf8_sig_json_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = '[{"id":"bom-1","question":"홍조?","answer":"진정 중심으로 관리합니다."}]'
            (root / "bom.json").write_text(payload, encoding="utf-8-sig")
            manifest = build_manifest(root, "71961", "test")
            profile = profile_json_files([root / "bom.json"])
            records, quarantine = canonicalize_manifest(root, manifest)
            self.assertEqual(profile["records_sampled"], 1)
            self.assertEqual(len(profile["failed_files"]), 0)
            self.assertEqual(len(records), 1)
            self.assertEqual(quarantine, [])

    def test_nested_aihub_json_and_csv_are_canonicalized(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            nested_json = root / "nested.json"
            nested_json.write_text(
                json.dumps(
                    {
                        "Data_info": {"Title": "홍조 피부 문서"},
                        "File_info": {"File Name": "홍조 피부 문서", "Purpose": "연구 목적"},
                        "Annotation_info": {"Main Keywords": "홍조, 민감성"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            csv_path = root / "survey.csv"
            csv_path.write_text(
                "No,성별,나이,얼굴 피부 타입,피부 고민 유형,고민부위\n1,여성,30,복합성,모공,볼\n",
                encoding="utf-8-sig",
            )
            manifest = build_manifest(root, "71886", "test")
            profile = profile_json_files([nested_json, csv_path])
            records, quarantine = canonicalize_manifest(root, manifest)
            self.assertEqual(profile["records_sampled"], 2)
            self.assertEqual(len(records), 2)
            self.assertEqual(quarantine, [])
            self.assertEqual({record.record_type for record in records}, {"document", "survey"})

    def test_non_json_files_are_quarantined_not_silently_dropped(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            note = root / "note.txt"
            note.write_text("plain text", encoding="utf-8")
            manifest = build_manifest(root, "71961", "test")
            records, quarantine = canonicalize_manifest(root, manifest)
            report = build_quality_report(records, quarantine)
            self.assertEqual(records, [])
            self.assertEqual(quarantine[0].reason_code, "unsupported_file_type")
            self.assertFalse(report.passed)

    def test_schema_cypher_contains_constraints_fulltext_and_vector(self) -> None:
        cypher = schema_cypher(include_vector=True)
        self.assertIn("CREATE CONSTRAINT dataset_id_unique", cypher)
        self.assertIn("CREATE CONSTRAINT image_id_unique", cypher)
        self.assertIn("CREATE FULLTEXT INDEX chunk_text_fulltext", cypher)
        self.assertIn("CREATE VECTOR INDEX chunk_embedding_vector", cypher)
        self.assertGreaterEqual(len(split_cypher(cypher)), 20)

    def test_readiness_queries_are_available(self) -> None:
        self.assertIn("future_cag_concern_to_ingredient", READINESS_QUERIES)
        self.assertIn("future_graphrag_chunk_expansion", READINESS_QUERIES)
        self.assertIn("MATCH", READINESS_QUERIES["future_graphrag_chunk_expansion"])

    def test_taxonomy_and_contracts_are_machine_readable(self) -> None:
        self.assertEqual(normalize_alias("SkinConcern", "홍조"), "redness")
        self.assertIn("Chunk", NODE_PROPERTY_CONTRACTS)
        self.assertIn("Image", NODE_PROPERTY_CONTRACTS)
        missing = missing_required_properties("Chunk", {"id", "text"})
        self.assertIn("source_document_id", missing)
        self.assertIn("source_qa_id", NODE_PROPERTY_CONTRACTS["Recommendation"])
        self.assertIn("source_chunk_id", NODE_PROPERTY_CONTRACTS["Evidence"])
        self.assertIn("build_id", missing_common_provenance({"id", "source_dataset_id"}))

    def test_cli_like_outputs_are_json_serializable(self) -> None:
        root = FIXTURES / "aihub_71886"
        manifest = build_manifest(root, "71886", "test")
        records, quarantine = canonicalize_manifest(root, manifest)
        report = build_quality_report(records, quarantine)

        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "quality.json"
            out.write_text(json.dumps(report.to_dict(), ensure_ascii=False), encoding="utf-8")
            loaded = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(loaded["total_records"], 2)
            self.assertEqual(loaded["duplicate_ids"], 0)

    def test_zip_scan_and_sample(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            zip_path = root / "sample.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("a.json", '{"id":"1","text":"hello"}')
                archive.writestr("b.jpg", b"fake")
            scan = scan_zip(zip_path)
            self.assertEqual(scan.entries, 2)
            self.assertEqual(scan.extension_counts[".json"], 1)
            output = root / "sampled"
            written = sample_zip_entries(zip_path, output, limit=10, extensions={".json"})
            self.assertEqual(len(written), 1)
            self.assertTrue((output / "a.json").exists())

    def test_self_signed_uri_conversion_is_explicit(self) -> None:
        self.assertEqual(
            allow_self_signed_scheme("neo4j+s://example.databases.neo4j.io"),
            "neo4j+ssc://example.databases.neo4j.io",
        )
        self.assertEqual(
            allow_self_signed_scheme("bolt+s://example:7687"),
            "bolt+ssc://example:7687",
        )
        self.assertEqual(allow_self_signed_scheme("neo4j://localhost"), "neo4j://localhost")

    def test_load_fails_before_connect_when_record_manifest_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            records = root / "records.jsonl"
            manifest = root / "manifest.jsonl"
            records.write_text(
                json.dumps(
                    {
                        "id": "record-1",
                        "source_dataset_id": "71961",
                        "source_file_id": "missing-source-file",
                        "source_record_id": "raw-1",
                        "record_type": "document",
                        "title": "sample",
                        "text": "sample text",
                        "content_hash": "hash",
                        "extraction_method": "fixture",
                        "confidence": 1.0,
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            manifest.write_text("", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing-source-file"):
                load_canonical_records(
                    uri="neo4j://not-used",
                    username="not-used",
                    password="not-used",
                    database="not-used",
                    manifest_paths=[manifest],
                    record_paths=[records],
                    build_id="test",
                )

    def test_zip_canonicalize_writes_manifest_batches_and_quality(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "aihub"
            zip_dir = root / "02.sample"
            zip_dir.mkdir(parents=True)
            zip_path = zip_dir / "sample.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("one.json", json.dumps({"title": "title", "text": "body"}))
                archive.writestr("two.csv", "No,name\n1,alpha\n")
                archive.writestr("image.jpg", b"fake")

            output = Path(temp) / "out"
            summary = canonicalize_zip_tree(root, output, batch_size=1)

            self.assertEqual(summary.zip_files, 1)
            self.assertEqual(summary.source_files, 3)
            self.assertEqual(summary.canonical_files, 2)
            self.assertEqual(summary.records, 2)
            self.assertEqual(summary.batches, 2)
            self.assertTrue((output / "manifest_full.jsonl").exists())
            self.assertTrue((output / "records" / "records_000001.jsonl").exists())
            quality = json.loads((output / "quality_full.json").read_text(encoding="utf-8"))
            self.assertTrue(quality["passed"])

    def test_extract_and_canonicalize_extracted_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "aihub"
            zip_dir = root / "02.sample"
            zip_dir.mkdir(parents=True)
            zip_path = zip_dir / "sample.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("nested/one.json", json.dumps({"title": "title", "text": "body"}))
                archive.writestr("nested/image.jpg", b"fake")

            raw = Path(temp) / "raw"
            extract_summary = extract_zip_tree(root, raw)
            self.assertEqual(extract_summary.zip_files, 1)
            self.assertEqual(extract_summary.files, 2)
            self.assertEqual(len(list(raw.rglob("one.json"))), 1)

            output = Path(temp) / "processed"
            build_summary = canonicalize_extracted_tree(raw, output, batch_size=1)
            self.assertEqual(build_summary.source_files, 2)
            self.assertEqual(build_summary.canonical_files, 1)
            self.assertEqual(build_summary.records, 1)
            quality = json.loads((output / "quality_full_extracted.json").read_text(encoding="utf-8"))
            self.assertTrue(quality["passed"])


if __name__ == "__main__":
    unittest.main()
