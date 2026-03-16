from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.services.board_import.hydrus_png import (
    decode_hydrus_png,
    inspect_hydrus_png,
    payload_to_json,
    payload_to_text,
)
from app.services.board_import.importer import run_simple_import, run_smoke_all
from app.services.board_import.presets import CORE_PRESETS, PRESETS, load_discovered_winner_catalog


def _write_output(path: str | None, data: bytes | str) -> None:
    if path is None:
        if isinstance(data, bytes):
            sys.stdout.buffer.write(data)
        else:
            sys.stdout.write(data)
            if not data.endswith("\n"):
                sys.stdout.write("\n")
        return

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    if isinstance(data, bytes):
        target.write_bytes(data)
    else:
        target.write_text(data, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="borooimport")
    subparsers = parser.add_subparsers(dest="command", required=True)

    importer = subparsers.add_parser("import", help="Import posts from a booru into NextBoo")
    importer.add_argument("-booru", "--booru", required=True, help="Source board preset, e.g. E621")
    importer.add_argument("-tags", "--tags", required=True, help="Comma-separated source tags")
    importer.add_argument("--limit", type=int, default=50, help="Maximum number of posts to fetch this run")
    importer.add_argument(
        "--hourly-limit",
        type=int,
        default=1000,
        help="Global import budget per hour",
    )
    importer.add_argument("--download-dir", help="Optional persistent download directory")
    importer.add_argument(
        "--enqueue-only",
        action="store_true",
        help="Upload into NextBoo and return after job acceptance without waiting for worker completion",
    )

    smoke = subparsers.add_parser(
        "smoke-all",
        help="Run a broad enqueue smoke test across all directly importable presets",
    )
    smoke.add_argument("--tags", default="1girl,furry", help="Fallback tags tried in order per preset")
    smoke.add_argument("--limit", type=int, default=3, help="Target number of queued files per preset")
    smoke.add_argument("--hourly-limit", type=int, default=5000, help="Temporary local budget for the smoke run")
    smoke.add_argument("--report", default="reports/smoke-all-report.json", help="Output report path")

    hydrus = subparsers.add_parser("hydrus", help="Hydrus preset inspection helpers")
    hydrus_subparsers = hydrus.add_subparsers(dest="hydrus_command", required=True)

    boards = subparsers.add_parser("boards", help="List supported source boards")
    boards.add_argument("--json", action="store_true", help="Emit JSON instead of plain text")
    boards.add_argument(
        "--all",
        action="store_true",
        help="List the full Hydrus winner catalog, including entries not yet directly importable by the CLI",
    )

    decode = hydrus_subparsers.add_parser("decode-png", help="Decode a Hydrus preset PNG")
    decode.add_argument("path")
    decode.add_argument(
        "--format",
        choices=("raw", "text", "json"),
        default="text",
        help="Output format for the decoded payload",
    )
    decode.add_argument("--output", help="Optional output file")

    inspect = hydrus_subparsers.add_parser(
        "inspect-png",
        help="Decode and structurally inspect a Hydrus preset PNG",
    )
    inspect.add_argument("path")
    inspect.add_argument("--json", action="store_true", help="Emit JSON report")
    inspect.add_argument("--output", help="Optional output file")
    inspect.add_argument("--max-depth", type=int, default=6)
    inspect.add_argument("--max-items", type=int, default=25)

    scan = hydrus_subparsers.add_parser(
        "scan-tree",
        help="Recursively inspect a directory of Hydrus preset PNGs",
    )
    scan.add_argument("root")
    scan.add_argument("--glob", default="*.png")
    scan.add_argument("--output", help="Optional output file")
    scan.add_argument("--max-depth", type=int, default=3)
    scan.add_argument("--max-items", type=int, default=12)

    return parser


def run_decode_png(args: argparse.Namespace) -> int:
    decoded = decode_hydrus_png(args.path)

    if args.format == "raw":
        _write_output(args.output, decoded.payload_bytes)
        return 0

    if args.format == "text":
        _write_output(args.output, payload_to_text(decoded.payload_bytes))
        return 0

    payload = payload_to_json(decoded.payload_bytes)
    _write_output(args.output, json.dumps(payload, indent=2, ensure_ascii=True))
    return 0


def run_inspect_png(args: argparse.Namespace) -> int:
    report = inspect_hydrus_png(
        args.path,
        max_depth=args.max_depth,
        max_items=args.max_items,
    )

    rendered = json.dumps(report, indent=2, ensure_ascii=True)
    _write_output(args.output, rendered)

    if not args.json and args.output is None:
        sys.stdout.write("\n")

    return 0


def run_scan_tree(args: argparse.Namespace) -> int:
    root = Path(args.root)
    reports: list[dict[str, object]] = []

    for path in sorted(root.rglob(args.glob)):
        if not path.is_file():
            continue

        try:
            report = inspect_hydrus_png(
                path,
                max_depth=args.max_depth,
                max_items=args.max_items,
            )
            reports.append(report)
        except Exception as exc:
            reports.append(
                {
                    "path": str(path),
                    "error": str(exc),
                }
            )

    rendered = json.dumps(
        {
            "root": str(root),
            "glob": args.glob,
            "count": len(reports),
            "reports": reports,
        },
        indent=2,
        ensure_ascii=True,
    )
    _write_output(args.output, rendered)
    return 0


def run_boards(args: argparse.Namespace) -> int:
    if args.all:
        payload = [
            {
                "name": item["name"],
                "family": item["family"],
                "site_url": item["candidate_url"],
                "search_url": item["candidate_url"],
                "hydrus_reference": f"docs/external/Hydrus-Presets-and-Scripts/Downloaders/{item['preset_path']}",
                "supported": item["supported"],
                "source_group": item["source_group"],
            }
            for item in load_discovered_winner_catalog()
        ]
    else:
        payload = [
            {
                "name": preset.name,
                "family": preset.family,
                "site_url": preset.site_url,
                "search_url": preset.search_url,
                "hydrus_reference": preset.hydrus_reference,
                "supported": True,
                "source_group": "core" if key in CORE_PRESETS else "generated",
            }
            for key, preset in sorted(PRESETS.items())
        ]
    if args.json:
        _write_output(None, json.dumps(payload, indent=2, ensure_ascii=True))
        return 0

    for item in payload:
        if args.all:
            marker = "supported" if item["supported"] else "catalog-only"
            sys.stdout.write(f"{item['name']} ({item['source_group']}, {marker})\n")
        else:
            sys.stdout.write(f"{item['name']} ({item['family']})\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "hydrus" and args.hydrus_command == "decode-png":
        return run_decode_png(args)

    if args.command == "hydrus" and args.hydrus_command == "inspect-png":
        return run_inspect_png(args)

    if args.command == "hydrus" and args.hydrus_command == "scan-tree":
        return run_scan_tree(args)

    if args.command == "import":
        return run_simple_import(args)

    if args.command == "smoke-all":
        return run_smoke_all(args)

    if args.command == "boards":
        return run_boards(args)

    parser.error("unknown command")
    return 2
