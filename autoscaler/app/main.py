import json
import math
import os
import time
from datetime import datetime, timezone

import docker
import psycopg
from redis import Redis


AUTOSCALER_STATUS_KEY = "nextboo:autoscaler:status"
UPLOAD_BALANCER_STATUS_KEY = "nextboo:upload-balancer:status"
UPLOAD_BALANCER_FORCE_KEY = "nextboo:upload-balancer:force"
AUTOSCALED_LABEL = "nextboo.autoscaled"

PIPELINE_STAGE_CONFIGS = {
    "scanning": {
        "service": "upload_scanner",
        "queue_name": "upload:stage:scan",
        "presence_pattern": "nextboo:upload-stage:scanning:*",
        "cost_weight": 1.0,
    },
    "dedupe": {
        "service": "upload_dedupe",
        "queue_name": "upload:stage:dedupe",
        "presence_pattern": "nextboo:upload-stage:dedupe:*",
        "cost_weight": 0.8,
    },
    "normalize": {
        "service": "upload_normalizer",
        "queue_name": "upload:stage:normalize",
        "presence_pattern": "nextboo:upload-stage:normalize:*",
        "cost_weight": 2.0,
    },
    "dispatch": {
        "service": "upload_dispatcher",
        "queue_name": "upload:stage:dispatch",
        "presence_pattern": "nextboo:upload-stage:dispatch:*",
        "cost_weight": 0.6,
    },
    "ingest_image": {
        "service": "worker",
        "queue_name": "jobs:ingest:camie",
        "presence_pattern": "nextboo:workers:image:active:*",
        "cost_weight": 2.5,
    },
    "ingest_video": {
        "service": "worker_video",
        "queue_name": "jobs:ingest:video",
        "presence_pattern": "nextboo:workers:video:active:*",
        "cost_weight": 3.0,
    },
}


def env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def postgres_dsn() -> str:
    return (
        f"postgresql://{env('POSTGRES_USER', 'nextboo')}:{env('POSTGRES_PASSWORD', 'nextboo')}"
        f"@{env('POSTGRES_HOST', 'postgres')}:{env('POSTGRES_PORT', '5432')}/{env('POSTGRES_DB', 'nextboo')}"
    )


def redis_client() -> Redis:
    return Redis.from_url(f"redis://{env('REDIS_HOST', 'redis')}:{env('REDIS_PORT', '6379')}/0", decode_responses=True)


def get_legacy_worker_settings() -> dict[str, int | bool]:
    defaults = {
        "autoscaler_enabled": False,
        "autoscaler_jobs_per_worker": 100,
        "autoscaler_min_workers": 1,
        "autoscaler_max_workers": 4,
        "autoscaler_poll_seconds": 30,
    }
    with psycopg.connect(postgres_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT key, value
                FROM app_settings
                WHERE key IN (
                    'autoscaler_enabled',
                    'autoscaler_jobs_per_worker',
                    'autoscaler_min_workers',
                    'autoscaler_max_workers',
                    'autoscaler_poll_seconds'
                )
                """
            )
            for key, value in cur.fetchall():
                if key == "autoscaler_enabled":
                    defaults[key] = value == "1"
                else:
                    defaults[key] = max(int(value), 1)
    if int(defaults["autoscaler_max_workers"]) < int(defaults["autoscaler_min_workers"]):
        defaults["autoscaler_max_workers"] = defaults["autoscaler_min_workers"]
    return defaults


def get_upload_pipeline_settings() -> dict[str, object]:
    defaults: dict[str, object] = {
        "upload_pipeline_balancer_enabled": False,
        "upload_pipeline_balancer_poll_seconds": 20,
        "upload_pipeline_balancer_flexible_slots": 8,
        "stages": {
            "scanning": {"min_workers": 1, "max_workers": 6, "jobs_per_worker": 100},
            "dedupe": {"min_workers": 1, "max_workers": 4, "jobs_per_worker": 200},
            "normalize": {"min_workers": 1, "max_workers": 8, "jobs_per_worker": 40},
            "dispatch": {"min_workers": 1, "max_workers": 3, "jobs_per_worker": 150},
            "ingest_image": {"min_workers": 1, "max_workers": 8, "jobs_per_worker": 25},
            "ingest_video": {"min_workers": 1, "max_workers": 4, "jobs_per_worker": 4},
        },
    }
    keys = [
        "upload_pipeline_balancer_enabled",
        "upload_pipeline_balancer_poll_seconds",
        "upload_pipeline_balancer_flexible_slots",
    ]
    for stage in PIPELINE_STAGE_CONFIGS:
        keys.extend(
            [
                f"upload_pipeline_stage_{stage}_min_workers",
                f"upload_pipeline_stage_{stage}_max_workers",
                f"upload_pipeline_stage_{stage}_jobs_per_worker",
            ]
        )
    with psycopg.connect(postgres_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT key, value
                FROM app_settings
                WHERE key = ANY(%s)
                """,
                (keys,),
            )
            for key, value in cur.fetchall():
                if key == "upload_pipeline_balancer_enabled":
                    defaults[key] = value == "1"
                elif key in {"upload_pipeline_balancer_poll_seconds", "upload_pipeline_balancer_flexible_slots"}:
                    defaults[key] = max(int(value), 0 if key.endswith("flexible_slots") else 5)
                else:
                    prefix = "upload_pipeline_stage_"
                    suffixes = ("_min_workers", "_max_workers", "_jobs_per_worker")
                    if not key.startswith(prefix):
                        continue
                    stage_part = key[len(prefix) :]
                    for suffix in suffixes:
                        if stage_part.endswith(suffix):
                            stage = stage_part[: -len(suffix)]
                            field = suffix.removeprefix("_")
                            if stage in defaults["stages"]:
                                defaults["stages"][stage][field] = max(int(value), 1)
                            break
    for stage_settings in defaults["stages"].values():
        if stage_settings["max_workers"] < stage_settings["min_workers"]:
            stage_settings["max_workers"] = stage_settings["min_workers"]
    return defaults


def list_service_containers(client: docker.DockerClient, service_name: str) -> tuple[list, list]:
    all_containers = client.containers.list(
        all=True,
        filters={"label": [f"com.docker.compose.service={service_name}"]},
    )
    base = [container for container in all_containers if container.labels.get(AUTOSCALED_LABEL) != "true"]
    autoscaled = [container for container in all_containers if container.labels.get(AUTOSCALED_LABEL) == "true"]
    return base, autoscaled


def build_volumes(template_container) -> dict:
    volumes: dict[str, dict[str, str]] = {}
    for mount in template_container.attrs.get("Mounts", []):
        if mount.get("Type") not in {"bind", "volume"}:
            continue
        source = mount.get("Name") or mount.get("Source")
        if not source:
            continue
        volumes[source] = {
            "bind": mount["Destination"],
            "mode": "rw" if mount.get("RW", True) else "ro",
        }
    return volumes


def scale_up(client: docker.DockerClient, template_container, target_total: int, current_total: int) -> int:
    created = 0
    template_container.reload()
    config = template_container.attrs["Config"]
    host_config = template_container.attrs["HostConfig"]
    network_names = list(template_container.attrs["NetworkSettings"]["Networks"].keys())
    network_name = network_names[0] if network_names else None
    volumes = build_volumes(template_container)
    restart_policy = host_config.get("RestartPolicy") or {"Name": "unless-stopped"}
    base_name = template_container.name
    existing_names = {container.name for container in client.containers.list(all=True)}

    next_index = current_total + 1
    while current_total + created < target_total:
        container_name = f"{base_name}-autoscaled-{next_index}"
        next_index += 1
        if container_name in existing_names:
            continue
        labels = dict(template_container.labels)
        labels[AUTOSCALED_LABEL] = "true"
        client.containers.run(
            image=template_container.image.tags[0] if template_container.image.tags else template_container.image.id,
            command=config.get("Cmd"),
            entrypoint=config.get("Entrypoint"),
            detach=True,
            environment=config.get("Env"),
            labels=labels,
            mem_limit=host_config.get("Memory") or None,
            nano_cpus=host_config.get("NanoCpus") or None,
            name=container_name,
            network=network_name,
            restart_policy=restart_policy,
            volumes=volumes,
            working_dir=config.get("WorkingDir") or None,
        )
        existing_names.add(container_name)
        created += 1
    return created


def scale_down(autoscaled_workers: list, excess: int) -> int:
    removed = 0
    for container in sorted(autoscaled_workers, key=lambda item: item.attrs.get("Created", ""), reverse=True)[:excess]:
        container.stop(timeout=10)
        container.remove(v=True, force=True)
        removed += 1
    return removed


def update_status(redis: Redis, **fields: str | int | None) -> None:
    payload = {key: ("" if value is None else str(value)) for key, value in fields.items()}
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    redis.hset(AUTOSCALER_STATUS_KEY, mapping=payload)


def active_workers_for_stage(redis: Redis, stage: str) -> list[str]:
    pattern = PIPELINE_STAGE_CONFIGS[stage]["presence_pattern"]
    prefix = pattern[:-1]
    return sorted(key.removeprefix(prefix) for key in redis.keys(pattern))


def queue_depth_for_stage(redis: Redis, stage: str) -> int:
    return int(redis.llen(PIPELINE_STAGE_CONFIGS[stage]["queue_name"]))


def oldest_queued_seconds_for_stage(stage: str) -> int:
    query = None
    if stage in {"scanning", "dedupe", "normalize", "dispatch"}:
        query = """
            SELECT EXTRACT(EPOCH FROM NOW() - MIN(last_stage_change_at))
            FROM upload_pipeline_items
            WHERE stage = %(stage)s
              AND status IN ('queued', 'running')
        """
    elif stage == "ingest_image":
        query = """
            SELECT EXTRACT(EPOCH FROM NOW() - MIN(created_at))
            FROM jobs
            WHERE queue_path = 'jobs:ingest:camie'
              AND status IN ('QUEUED', 'RETRYING', 'RUNNING')
        """
    elif stage == "ingest_video":
        query = """
            SELECT EXTRACT(EPOCH FROM NOW() - MIN(created_at))
            FROM jobs
            WHERE queue_path = 'jobs:ingest:video'
              AND status IN ('QUEUED', 'RETRYING', 'RUNNING')
        """
    if query is None:
        return 0
    with psycopg.connect(postgres_dsn()) as conn:
        with conn.cursor() as cur:
            if "%(stage)s" in query:
                cur.execute(query, {"stage": stage})
            else:
                cur.execute(query)
            value = cur.fetchone()[0]
    if value is None:
        return 0
    return max(int(value), 0)


def compute_stage_plan(settings: dict[str, object], redis: Redis) -> dict[str, dict[str, object]]:
    plans: dict[str, dict[str, object]] = {}
    for stage, config in PIPELINE_STAGE_CONFIGS.items():
        stage_settings = settings["stages"][stage]
        queue_depth = queue_depth_for_stage(redis, stage)
        oldest_seconds = oldest_queued_seconds_for_stage(stage)
        jobs_per_worker = max(int(stage_settings["jobs_per_worker"]), 1)
        min_workers = max(int(stage_settings["min_workers"]), 1)
        max_workers = max(int(stage_settings["max_workers"]), min_workers)
        queue_pressure = queue_depth / jobs_per_worker if queue_depth else 0
        age_pressure = min(oldest_seconds / 120.0, 5.0)
        score = (queue_pressure + age_pressure) * float(config["cost_weight"])
        desired_extra = min(
            max_workers - min_workers,
            max(0, math.ceil(queue_pressure + (1 if oldest_seconds >= 120 else 0))),
        )
        recommended_workers = min(max_workers, min_workers + desired_extra)
        plans[stage] = {
            "stage": stage,
            "service": config["service"],
            "min_workers": min_workers,
            "max_workers": max_workers,
            "jobs_per_worker": jobs_per_worker,
            "queue_depth": queue_depth,
            "oldest_queued_seconds": oldest_seconds,
            "score": score,
            "desired_extra": desired_extra,
            "recommended_workers": recommended_workers,
        }

    return plans


def update_upload_balancer_status(redis: Redis, plans: dict[str, dict[str, object]], summary: str | None, error: str | None) -> None:
    mapping: dict[str, str] = {
        "last_rebalance_at": datetime.now(timezone.utc).isoformat(),
        "last_rebalance_summary": summary or "",
        "last_error": error or "",
    }
    for stage, plan in plans.items():
        mapping[f"{stage}:recommended_workers"] = str(plan["recommended_workers"])
        mapping[f"{stage}:queue_depth"] = str(plan["queue_depth"])
        mapping[f"{stage}:oldest_queued_seconds"] = str(plan["oldest_queued_seconds"])
        mapping[f"{stage}:score"] = f"{float(plan['score']):.3f}"
        mapping[f"{stage}:current_workers"] = str(plan.get("current_workers", 0))
    redis.hset(UPLOAD_BALANCER_STATUS_KEY, mapping=mapping)


def update_legacy_from_image_stage(redis: Redis, plans: dict[str, dict[str, object]]) -> None:
    image_plan = plans["ingest_image"]
    active_workers = active_workers_for_stage(redis, "ingest_image")
    update_status(
        redis,
        enabled=1,
        queue_depth=int(image_plan["queue_depth"]),
        current_worker_count=int(image_plan.get("current_workers", len(active_workers))),
        recommended_worker_count=int(image_plan["recommended_workers"]),
        active_workers=json.dumps(active_workers),
        last_scale_action="managed_by_pipeline_balancer",
        last_scale_at=datetime.now(timezone.utc).isoformat(),
        last_error=None,
    )


def sleep_with_interrupt(redis: Redis, seconds: int) -> None:
    remaining = max(int(seconds), 1)
    while remaining > 0:
        if redis.exists(UPLOAD_BALANCER_FORCE_KEY):
            redis.delete(UPLOAD_BALANCER_FORCE_KEY)
            return
        time.sleep(1)
        remaining -= 1


def rebalance_pipeline(client: docker.DockerClient, redis: Redis) -> None:
    settings = get_upload_pipeline_settings()
    plans = compute_stage_plan(settings, redis)
    change_messages: list[str] = []

    for stage, plan in plans.items():
        base_workers, autoscaled_workers = list_service_containers(client, plan["service"])
        current_total = len(base_workers) + len(autoscaled_workers)
        plan["current_workers"] = current_total
        if not base_workers:
            update_upload_balancer_status(redis, plans, None, f"No base container found for {plan['service']}")
            update_legacy_from_image_stage(redis, plans)
            return

        target_total = int(plan["recommended_workers"]) if bool(settings["upload_pipeline_balancer_enabled"]) else int(plan["min_workers"])
        if current_total < target_total:
            created = scale_up(client, base_workers[0], target_total, current_total)
            if created:
                change_messages.append(f"{stage}+{created}")
            plan["current_workers"] = current_total + created
        elif current_total > target_total:
            removed = scale_down(autoscaled_workers, current_total - target_total)
            if removed:
                change_messages.append(f"{stage}-{removed}")
            plan["current_workers"] = current_total - removed

    summary = ", ".join(change_messages) if change_messages else "steady"
    update_upload_balancer_status(redis, plans, summary, None)
    update_legacy_from_image_stage(redis, plans)


def run_legacy_worker_autoscaler(client: docker.DockerClient, redis: Redis) -> None:
    settings = get_legacy_worker_settings()
    queue_depth = int(redis.llen(env("QUEUE_NAME", "jobs:ingest:camie")))
    base_workers, autoscaled_workers = list_service_containers(client, "worker")
    current_total = len(base_workers) + len(autoscaled_workers)
    jobs_per_worker = int(settings["autoscaler_jobs_per_worker"])
    min_workers = int(settings["autoscaler_min_workers"])
    max_workers = int(settings["autoscaler_max_workers"])
    recommended_total = max(min_workers, min(max_workers, max(1, math.ceil(queue_depth / jobs_per_worker) if queue_depth else min_workers)))
    active_workers = active_workers_for_stage(redis, "ingest_image")

    try:
        if not base_workers:
            update_status(
                redis,
                enabled=int(bool(settings["autoscaler_enabled"])),
                queue_depth=queue_depth,
                current_worker_count=current_total,
                recommended_worker_count=recommended_total,
                active_workers=json.dumps(active_workers),
                last_error="No base worker container found",
            )
            return

        if bool(settings["autoscaler_enabled"]):
            if current_total < recommended_total:
                created = scale_up(client, base_workers[0], recommended_total, current_total)
                update_status(
                    redis,
                    enabled=1,
                    queue_depth=queue_depth,
                    current_worker_count=current_total + created,
                    recommended_worker_count=recommended_total,
                    active_workers=json.dumps(active_workers),
                    last_scale_action=f"scale_up:{created}",
                    last_scale_at=datetime.now(timezone.utc).isoformat(),
                    last_error=None,
                )
            elif current_total > recommended_total:
                removed = scale_down(autoscaled_workers, current_total - recommended_total)
                update_status(
                    redis,
                    enabled=1,
                    queue_depth=queue_depth,
                    current_worker_count=current_total - removed,
                    recommended_worker_count=recommended_total,
                    active_workers=json.dumps(active_workers),
                    last_scale_action=f"scale_down:{removed}",
                    last_scale_at=datetime.now(timezone.utc).isoformat(),
                    last_error=None,
                )
            else:
                update_status(
                    redis,
                    enabled=1,
                    queue_depth=queue_depth,
                    current_worker_count=current_total,
                    recommended_worker_count=recommended_total,
                    active_workers=json.dumps(active_workers),
                    last_error=None,
                )
        else:
            update_status(
                redis,
                enabled=0,
                queue_depth=queue_depth,
                current_worker_count=current_total,
                recommended_worker_count=recommended_total,
                active_workers=json.dumps(active_workers),
                last_error=None,
            )
    except Exception as exc:
        update_status(
            redis,
            enabled=int(bool(settings["autoscaler_enabled"])),
            queue_depth=queue_depth,
            current_worker_count=current_total,
            recommended_worker_count=recommended_total,
            active_workers=json.dumps(active_workers),
            last_error=str(exc),
        )


def main() -> None:
    docker_client = docker.from_env()
    redis = redis_client()

    while True:
        pipeline_settings = get_upload_pipeline_settings()
        try:
            if bool(pipeline_settings["upload_pipeline_balancer_enabled"]):
                rebalance_pipeline(docker_client, redis)
                sleep_seconds = int(pipeline_settings["upload_pipeline_balancer_poll_seconds"])
            else:
                run_legacy_worker_autoscaler(docker_client, redis)
                sleep_seconds = int(get_legacy_worker_settings()["autoscaler_poll_seconds"])
        except Exception as exc:
            redis.hset(
                UPLOAD_BALANCER_STATUS_KEY,
                mapping={
                    "last_rebalance_at": datetime.now(timezone.utc).isoformat(),
                    "last_rebalance_summary": "",
                    "last_error": str(exc),
                },
            )
            sleep_seconds = int(pipeline_settings["upload_pipeline_balancer_poll_seconds"])
        sleep_with_interrupt(redis, max(sleep_seconds, 5))


if __name__ == "__main__":
    main()
