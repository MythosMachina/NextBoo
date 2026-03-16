from __future__ import annotations

import json
import tempfile
from pathlib import Path

import requests

from app.services.board_import.adapters import build_adapter
from app.services.board_import.models import RemotePost
from app.services.board_import.nextboo import NextBooClient, NextBooConfig
from app.services.board_import.presets import PRESETS, get_preset
from app.services.board_import.state import HourlyBudget

FIXED_NEXTBOO_URL = "http://192.168.1.57:18000"
FIXED_NEXTBOO_USERNAME = "boroouploader"
FIXED_NEXTBOO_PASSWORD = "BorooUploader123"
FIXED_NEXTBOO_ADMIN_USERNAME = "admin"
FIXED_NEXTBOO_ADMIN_PASSWORD = "admin"


def parse_csv_tags(raw_tags: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for item in raw_tags.split(","):
        normalized = item.strip().lower().replace(" ", "_")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        values.append(normalized)
    return values


def build_nextboo_config() -> NextBooConfig:
    return NextBooConfig(
        base_url=FIXED_NEXTBOO_URL,
        username=FIXED_NEXTBOO_USERNAME,
        password=FIXED_NEXTBOO_PASSWORD,
        admin_username=FIXED_NEXTBOO_ADMIN_USERNAME,
        admin_password=FIXED_NEXTBOO_ADMIN_PASSWORD,
    )


def download_remote_post(session: requests.Session, post: RemotePost, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    local_path = target_dir / f"{post.post_id}_{post.filename}"
    with session.get(post.file_url, stream=True, timeout=120) as response:
        response.raise_for_status()
        with local_path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
    return local_path


def run_simple_import(args) -> int:
    preset = get_preset(args.booru)
    tags = parse_csv_tags(args.tags)
    if not tags:
        raise RuntimeError("At least one tag is required")

    limit = args.limit
    budget = HourlyBudget(hourly_limit=args.hourly_limit)
    remaining = budget.remaining()
    if remaining <= 0:
        raise RuntimeError("Hourly import budget exhausted")

    fetch_limit = min(limit, remaining)
    adapter = build_adapter(preset)
    posts = adapter.search_posts(tags, fetch_limit)

    if not posts:
        print("No remote posts found.")
        return 0

    nextboo = NextBooClient(build_nextboo_config())
    nextboo.login()

    if args.download_dir:
        download_root = Path(args.download_dir)
        download_root.mkdir(parents=True, exist_ok=True)
        context = None
    else:
        context = tempfile.TemporaryDirectory(prefix="borooimport_")
        download_root = Path(context.name)

    downloaded = 0
    skipped = 0
    uploaded = 0
    staged: list[tuple[RemotePost, Path]] = []

    try:
        for post in posts:
            if budget.seen(post.board, post.post_id):
                skipped += 1
                continue

            if budget.remaining() <= 0:
                print("Hourly import budget reached. Stopping.")
                break

            local_path = download_remote_post(adapter.session, post, download_root)
            downloaded += 1
            staged.append((post, local_path))

        if not staged:
            print(
                f"Finished import: fetched={len(posts)} downloaded={downloaded} uploaded={uploaded} skipped={skipped} remaining_budget={budget.remaining()}"
            )
            return 0

        upload_payload = nextboo.upload_files([(local_path, post.post_id) for post, local_path in staged])
        accepted_by_key = {str(item["client_key"]): int(item["job_id"]) for item in upload_payload["data"]}
        for rejection in upload_payload["rejected"]:
            if rejection["error"] == "Duplicate file already exists in the gallery.":
                skipped += 1
                print(f"Skipped duplicate {preset.name}:{rejection['client_key']}")
                continue
            raise RuntimeError(f"Upload rejected for {rejection['filename']}: {rejection['error']}")

        if args.enqueue_only:
            for post, _local_path in staged:
                job_id = accepted_by_key.get(post.post_id)
                if job_id is None:
                    continue
                budget.record(post.board, post.post_id, nextboo_image_id=None)
                uploaded += 1
                print(f"Enqueued {post.board}:{post.post_id} -> job {job_id}")
        else:
            known_upload_ids = set(nextboo.list_my_upload_ids())
            for post, _local_path in staged:
                job_id = accepted_by_key.get(post.post_id)
                if job_id is None:
                    continue
                image_id = nextboo.wait_for_job(job_id, known_upload_ids=known_upload_ids)
                nextboo.add_tags(image_id, post.tags)
                budget.record(post.board, post.post_id, nextboo_image_id=image_id)
                uploaded += 1
                known_upload_ids.add(image_id)
                print(f"Imported {post.board}:{post.post_id} -> {image_id}")
    finally:
        if context is not None:
            context.cleanup()

    print(
        f"Finished import: fetched={len(posts)} downloaded={downloaded} uploaded={uploaded} skipped={skipped} remaining_budget={budget.remaining()}"
    )
    return 0


def run_smoke_all(args) -> int:
    tag_candidates = [tag.strip().lower().replace(" ", "_") for tag in args.tags.split(",") if tag.strip()]
    if not tag_candidates:
        raise RuntimeError("At least one fallback tag is required")

    nextboo = NextBooClient(build_nextboo_config())
    nextboo.login()
    admin = nextboo.admin_session()
    original_limits = nextboo.get_rate_limits(admin)
    boosted_limits = dict(original_limits)
    boosted_limits["rate_limit_upload_max_requests"] = max(boosted_limits["rate_limit_upload_max_requests"], 2000)
    boosted_limits["rate_limit_login_max_requests"] = max(boosted_limits["rate_limit_login_max_requests"], 2000)
    nextboo.patch_rate_limits(admin, boosted_limits)

    budget = HourlyBudget(hourly_limit=max(args.hourly_limit, 5000))
    results: list[dict[str, object]] = []
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        for preset in sorted(PRESETS.values(), key=lambda item: item.name.lower()):
            adapter = build_adapter(preset)
            search_error = None
            selected_tag = None
            posts: list[RemotePost] = []

            for candidate in tag_candidates:
                try:
                    fetched = adapter.search_posts([candidate], max(args.limit * 10, args.limit))
                except Exception as exc:  # noqa: BLE001
                    search_error = f"{type(exc).__name__}: {exc}"
                    continue
                filtered = [post for post in fetched if not budget.seen(post.board, post.post_id)]
                if filtered:
                    selected_tag = candidate
                    posts = filtered[: args.limit]
                    break

            result: dict[str, object] = {
                "preset": preset.name,
                "family": preset.family,
                "selected_tag": selected_tag,
                "queued": 0,
                "status": "fail",
                "reason": search_error or "no_posts",
            }

            if not posts:
                print(f"[FAIL] {preset.name}: {result['reason']}")
                results.append(result)
                continue

            with tempfile.TemporaryDirectory(prefix="borooimport_smoke_") as temp_dir:
                temp_root = Path(temp_dir)
                staged: list[tuple[RemotePost, Path]] = []
                for post in posts:
                    try:
                        local_path = download_remote_post(adapter.session, post, temp_root)
                    except Exception as exc:  # noqa: BLE001
                        result["reason"] = f"download_failed: {type(exc).__name__}: {exc}"
                        break
                    staged.append((post, local_path))

                if len(staged) < args.limit:
                    if result["reason"] == "no_posts":
                        result["reason"] = "download_failed"
                    print(f"[FAIL] {preset.name}: {result['reason']}")
                    results.append(result)
                    continue

                try:
                    upload_payload = nextboo.upload_files([(local_path, post.post_id) for post, local_path in staged])
                except Exception as exc:  # noqa: BLE001
                    result["reason"] = f"upload_failed: {type(exc).__name__}: {exc}"
                    print(f"[FAIL] {preset.name}: {result['reason']}")
                    results.append(result)
                    continue

                accepted_by_key = {str(item["client_key"]): int(item["job_id"]) for item in upload_payload["data"]}
                duplicate_count = 0
                other_rejection = None
                for rejection in upload_payload["rejected"]:
                    if rejection["error"] == "Duplicate file already exists in the gallery.":
                        duplicate_count += 1
                        continue
                    other_rejection = f"{rejection['filename']}: {rejection['error']}"
                    break

                if other_rejection is not None:
                    result["reason"] = f"upload_rejected: {other_rejection}"
                    print(f"[FAIL] {preset.name}: {result['reason']}")
                    results.append(result)
                    continue

                queued_posts = [post for post, _ in staged if post.post_id in accepted_by_key]
                for post in queued_posts:
                    budget.record(post.board, post.post_id, nextboo_image_id=None)

                result["queued"] = len(queued_posts)
                if len(queued_posts) >= args.limit:
                    result["status"] = "ok"
                    result["reason"] = "queued"
                    print(f"[ OK ] {preset.name}: queued={len(queued_posts)} tag={selected_tag}")
                else:
                    result["reason"] = f"queued={len(queued_posts)} duplicate={duplicate_count}"
                    print(f"[FAIL] {preset.name}: {result['reason']}")
                results.append(result)
    finally:
        nextboo.patch_rate_limits(admin, original_limits)
        admin.close()

    report_path.write_text(json.dumps({"count": len(results), "results": results}, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    ok_count = sum(1 for item in results if item["status"] == "ok")
    fail_count = len(results) - ok_count
    print(f"Smoke complete: total={len(results)} ok={ok_count} fail={fail_count} report={report_path}")
    return 0 if fail_count == 0 else 1
