"""Command line entrypoint for local DB-build artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .canonical import canonicalize_manifest
from .env import neo4j_config
from .extracted import canonicalize_extracted_tree, extract_zip_tree
from .graph_loader import apply_schema, load_canonical_records, load_images_from_manifest, load_record_batches, verify_counts
from .io import write_jsonl
from .manifest import build_manifest
from .profile import profile_json_files
from .quality import build_quality_report
from .schema import READINESS_QUERIES, schema_cypher
from .ziptools import TEXT_EXTENSIONS, sample_zip_entries, write_scan_report
from .zipbatch import canonicalize_zip_tree


def _cmd_manifest(args: argparse.Namespace) -> int:
    rows = build_manifest(Path(args.dataset_root), args.dataset_id, args.manifest_version)
    write_jsonl(Path(args.output), [row.to_dict() for row in rows])
    print(f"wrote {len(rows)} manifest rows to {args.output}")
    return 0


def _cmd_profile(args: argparse.Namespace) -> int:
    root = Path(args.dataset_root)
    paths = sorted(path for path in root.rglob("*") if path.is_file())
    report = profile_json_files(paths, args.sample_limit)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"profiled {report['records_sampled']} records into {args.output}")
    if report["records_sampled"] == 0 and not args.allow_empty:
        return 2
    if report["failed_files"] and not args.allow_errors:
        return 2
    return 0


def _cmd_canonicalize(args: argparse.Namespace) -> int:
    root = Path(args.dataset_root)
    manifest = build_manifest(root, args.dataset_id, args.manifest_version)
    records, quarantine = canonicalize_manifest(root, manifest)
    write_jsonl(Path(args.records_output), [record.to_dict() for record in records])
    write_jsonl(Path(args.quarantine_output), [item.to_dict() for item in quarantine])
    report = build_quality_report(records, quarantine)
    Path(args.quality_output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.quality_output).write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"canonicalized {len(records)} records; quarantined {len(quarantine)}")
    return 0 if report.passed else 2


def _cmd_schema(args: argparse.Namespace) -> int:
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(schema_cypher(include_vector=args.include_vector), encoding="utf-8")
    print(f"wrote schema Cypher to {args.output}")
    return 0


def _cmd_readiness(args: argparse.Namespace) -> int:
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    for name, query in READINESS_QUERIES.items():
        (output / f"{name}.cypher").write_text(query + "\n", encoding="utf-8")
    print(f"wrote {len(READINESS_QUERIES)} readiness queries to {output}")
    return 0


def _cmd_scan_zip(args: argparse.Namespace) -> int:
    scans = write_scan_report(Path(args.root), Path(args.output))
    print(f"scanned {len(scans)} zip files into {args.output}")
    return 0 if scans else 2


def _cmd_sample_zip(args: argparse.Namespace) -> int:
    extensions = {ext if ext.startswith(".") else f".{ext}" for ext in args.extensions.split(",")}
    written = sample_zip_entries(Path(args.zip_path), Path(args.output), args.limit, extensions)
    print(f"sampled {len(written)} files into {args.output}")
    return 0 if written else 2


def _cmd_auradb_schema(args: argparse.Namespace) -> int:
    config = neo4j_config(Path(args.env), allow_self_signed=args.allow_self_signed_cert)
    count = apply_schema(**config, include_vector=args.include_vector)
    print(f"applied {count} schema statements to AuraDB database {config['database']}")
    return 0


def _cmd_auradb_load(args: argparse.Namespace) -> int:
    config = neo4j_config(Path(args.env), allow_self_signed=args.allow_self_signed_cert)
    summary = load_canonical_records(
        **config,
        manifest_paths=[Path(path) for path in args.manifest],
        record_paths=[Path(path) for path in args.records],
        build_id=args.build_id,
        limit=args.limit,
    )
    print(json.dumps(summary.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0


def _cmd_auradb_verify(args: argparse.Namespace) -> int:
    config = neo4j_config(Path(args.env), allow_self_signed=args.allow_self_signed_cert)
    counts = verify_counts(**config)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(counts, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(counts, ensure_ascii=False, sort_keys=True))
    return 0 if counts["OrphanChunk"] == 0 and counts["MissingProvenance"] == 0 else 2


def _cmd_auradb_load_batch_dir(args: argparse.Namespace) -> int:
    config = neo4j_config(Path(args.env), allow_self_signed=args.allow_self_signed_cert)
    summary = load_record_batches(
        **config,
        manifest_path=Path(args.manifest),
        records_dir=Path(args.records_dir),
        build_id=args.build_id,
        load_images=args.load_images,
    )
    print(json.dumps(summary.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0


def _cmd_auradb_load_images(args: argparse.Namespace) -> int:
    config = neo4j_config(Path(args.env), allow_self_signed=args.allow_self_signed_cert)
    count = load_images_from_manifest(
        **config,
        manifest_path=Path(args.manifest),
        build_id=args.build_id,
    )
    print(json.dumps({"images": count}, ensure_ascii=False, sort_keys=True))
    return 0


def _cmd_zip_canonicalize(args: argparse.Namespace) -> int:
    summary = canonicalize_zip_tree(
        root=Path(args.root),
        output_dir=Path(args.output_dir),
        batch_size=args.batch_size,
        manifest_version=args.manifest_version,
        max_entries=args.max_entries,
    )
    print(json.dumps(summary.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if summary.records else 2


def _cmd_extract_zip_tree(args: argparse.Namespace) -> int:
    summary = extract_zip_tree(Path(args.root), Path(args.output_dir))
    print(json.dumps(summary.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if summary.files else 2


def _cmd_canonicalize_extracted(args: argparse.Namespace) -> int:
    summary = canonicalize_extracted_tree(
        root=Path(args.root),
        output_dir=Path(args.output_dir),
        batch_size=args.batch_size,
        manifest_version=args.manifest_version,
    )
    print(json.dumps(summary.to_dict(), ensure_ascii=False, sort_keys=True))
    return 0 if summary.records else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aihub-auradb")
    sub = parser.add_subparsers(required=True)

    manifest = sub.add_parser("manifest")
    manifest.add_argument("--dataset-root", required=True)
    manifest.add_argument("--dataset-id", required=True)
    manifest.add_argument("--manifest-version", default="local")
    manifest.add_argument("--output", required=True)
    manifest.set_defaults(func=_cmd_manifest)

    profile = sub.add_parser("profile")
    profile.add_argument("--dataset-root", required=True)
    profile.add_argument("--sample-limit", type=int, default=100)
    profile.add_argument("--output", required=True)
    profile.add_argument("--allow-empty", action="store_true")
    profile.add_argument("--allow-errors", action="store_true")
    profile.set_defaults(func=_cmd_profile)

    canonicalize = sub.add_parser("canonicalize")
    canonicalize.add_argument("--dataset-root", required=True)
    canonicalize.add_argument("--dataset-id", required=True)
    canonicalize.add_argument("--manifest-version", default="local")
    canonicalize.add_argument("--records-output", required=True)
    canonicalize.add_argument("--quarantine-output", required=True)
    canonicalize.add_argument("--quality-output", required=True)
    canonicalize.set_defaults(func=_cmd_canonicalize)

    schema = sub.add_parser("schema")
    schema.add_argument("--output", required=True)
    schema.add_argument("--include-vector", action="store_true")
    schema.set_defaults(func=_cmd_schema)

    readiness = sub.add_parser("readiness")
    readiness.add_argument("--output", required=True)
    readiness.set_defaults(func=_cmd_readiness)

    scan_zip = sub.add_parser("scan-zip")
    scan_zip.add_argument("--root", required=True)
    scan_zip.add_argument("--output", required=True)
    scan_zip.set_defaults(func=_cmd_scan_zip)

    sample_zip = sub.add_parser("sample-zip")
    sample_zip.add_argument("--zip-path", required=True)
    sample_zip.add_argument("--limit", type=int, default=300)
    sample_zip.add_argument("--extensions", default=",".join(sorted(TEXT_EXTENSIONS)))
    sample_zip.add_argument("--output", required=True)
    sample_zip.set_defaults(func=_cmd_sample_zip)

    zip_canonicalize = sub.add_parser("zip-canonicalize")
    zip_canonicalize.add_argument("--root", required=True)
    zip_canonicalize.add_argument("--output-dir", required=True)
    zip_canonicalize.add_argument("--batch-size", type=int, default=1000)
    zip_canonicalize.add_argument("--manifest-version", default="zip-full")
    zip_canonicalize.add_argument("--max-entries", type=int)
    zip_canonicalize.set_defaults(func=_cmd_zip_canonicalize)

    extract_zip_tree_cmd = sub.add_parser("extract-zip-tree")
    extract_zip_tree_cmd.add_argument("--root", required=True)
    extract_zip_tree_cmd.add_argument("--output-dir", required=True)
    extract_zip_tree_cmd.set_defaults(func=_cmd_extract_zip_tree)

    canonicalize_extracted = sub.add_parser("canonicalize-extracted")
    canonicalize_extracted.add_argument("--root", required=True)
    canonicalize_extracted.add_argument("--output-dir", required=True)
    canonicalize_extracted.add_argument("--batch-size", type=int, default=1000)
    canonicalize_extracted.add_argument("--manifest-version", default="extracted-full")
    canonicalize_extracted.set_defaults(func=_cmd_canonicalize_extracted)

    auradb_schema = sub.add_parser("auradb-schema")
    auradb_schema.add_argument("--env", default=".env")
    auradb_schema.add_argument("--include-vector", action="store_true")
    auradb_schema.add_argument(
        "--allow-self-signed-cert",
        action="store_true",
        help="Convert +s URI schemes to +ssc for environments whose TLS chain rejects the Aura certificate path.",
    )
    auradb_schema.set_defaults(func=_cmd_auradb_schema)

    auradb_load = sub.add_parser("auradb-load")
    auradb_load.add_argument("--env", default=".env")
    auradb_load.add_argument("--manifest", action="append", required=True)
    auradb_load.add_argument("--records", action="append", required=True)
    auradb_load.add_argument("--build-id", required=True)
    auradb_load.add_argument("--limit", type=int)
    auradb_load.add_argument(
        "--allow-self-signed-cert",
        action="store_true",
        help="Convert +s URI schemes to +ssc for environments whose TLS chain rejects the Aura certificate path.",
    )
    auradb_load.set_defaults(func=_cmd_auradb_load)

    auradb_load_batch_dir = sub.add_parser("auradb-load-batch-dir")
    auradb_load_batch_dir.add_argument("--env", default=".env")
    auradb_load_batch_dir.add_argument("--manifest", required=True)
    auradb_load_batch_dir.add_argument("--records-dir", required=True)
    auradb_load_batch_dir.add_argument("--build-id", required=True)
    auradb_load_batch_dir.add_argument("--load-images", action="store_true")
    auradb_load_batch_dir.add_argument(
        "--allow-self-signed-cert",
        action="store_true",
        help="Convert +s URI schemes to +ssc for environments whose TLS chain rejects the Aura certificate path.",
    )
    auradb_load_batch_dir.set_defaults(func=_cmd_auradb_load_batch_dir)

    auradb_load_images = sub.add_parser("auradb-load-images")
    auradb_load_images.add_argument("--env", default=".env")
    auradb_load_images.add_argument("--manifest", required=True)
    auradb_load_images.add_argument("--build-id", required=True)
    auradb_load_images.add_argument(
        "--allow-self-signed-cert",
        action="store_true",
        help="Convert +s URI schemes to +ssc for environments whose TLS chain rejects the Aura certificate path.",
    )
    auradb_load_images.set_defaults(func=_cmd_auradb_load_images)

    auradb_verify = sub.add_parser("auradb-verify")
    auradb_verify.add_argument("--env", default=".env")
    auradb_verify.add_argument("--output", default="reports/auradb_verify.json")
    auradb_verify.add_argument(
        "--allow-self-signed-cert",
        action="store_true",
        help="Convert +s URI schemes to +ssc for environments whose TLS chain rejects the Aura certificate path.",
    )
    auradb_verify.set_defaults(func=_cmd_auradb_verify)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
