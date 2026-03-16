import json
import math
import os
import time
from datetime import datetime, timezone

import docker
import psycopg
from redis import Redis


AUTOSCALER_STATUS_KEY = "nextboo:autoscaler:status"
AUTOSCALED_LABEL = "nextboo.autoscaled"


def env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def postgres_dsn() -> str:
    return (
        f"postgresql://{env('POSTGRES_USER', 'nextboo')}:{env('POSTGRES_PASSWORD', 'nextboo')}"
        f"@{env('POSTGRES_HOST', 'postgres')}:{env('POSTGRES_PORT', '5432')}/{env('POSTGRES_DB', 'nextboo')}"
    )


def redis_client() -> Redis:
    return Redis.from_url(f"redis://{env('REDIS_HOST', 'redis')}:{env('REDIS_PORT', '6379')}/0", decode_responses=True)


def get_settings() -> dict[str, int | bool]:
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


def list_worker_containers(client: docker.DockerClient) -> tuple[list, list]:
    all_workers = client.containers.list(
        all=True,
        filters={"label": ["com.docker.compose.service=worker"]},
    )
    base_workers = [container for container in all_workers if container.labels.get(AUTOSCALED_LABEL) != "true"]
    autoscaled_workers = [container for container in all_workers if container.labels.get(AUTOSCALED_LABEL) == "true"]
    return base_workers, autoscaled_workers


def build_volumes(template_container) -> dict:
    volumes: dict[str, dict[str, str]] = {}
    for mount in template_container.attrs.get("Mounts", []):
        if mount.get("Type") != "bind":
            continue
        volumes[mount["Source"]] = {
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

    for index in range(current_total + 1, target_total + 1):
        container_name = f"{base_name}-autoscaled-{index}"
        while container_name in existing_names:
            index += 1
            container_name = f"{base_name}-autoscaled-{index}"
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
    sorted_workers = sorted(autoscaled_workers, key=lambda item: item.attrs.get("Created", ""), reverse=True)
    for container in sorted_workers[:excess]:
        container.stop(timeout=10)
        container.remove(v=True, force=True)
        removed += 1
    return removed


def update_status(redis: Redis, **fields: str | int | None) -> None:
    payload = {key: ("" if value is None else str(value)) for key, value in fields.items()}
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    redis.hset(AUTOSCALER_STATUS_KEY, mapping=payload)


def main() -> None:
    docker_client = docker.from_env()
    redis = redis_client()

    while True:
        settings = get_settings()
        queue_depth = int(redis.llen(env("QUEUE_NAME", "jobs:ingest:camie")))
        base_workers, autoscaled_workers = list_worker_containers(docker_client)
        current_total = len(base_workers) + len(autoscaled_workers)
        jobs_per_worker = int(settings["autoscaler_jobs_per_worker"])
        min_workers = int(settings["autoscaler_min_workers"])
        max_workers = int(settings["autoscaler_max_workers"])
        recommended_total = max(min_workers, min(max_workers, max(1, math.ceil(queue_depth / jobs_per_worker) if queue_depth else min_workers)))
        active_workers = sorted(
            key.removeprefix("nextboo:workers:active:")
            for key in redis.keys("nextboo:workers:active:*")
        )

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
                time.sleep(int(settings["autoscaler_poll_seconds"]))
                continue

            if bool(settings["autoscaler_enabled"]):
                if current_total < recommended_total:
                    created = scale_up(docker_client, base_workers[0], recommended_total, current_total)
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
                    removable = max(current_total - recommended_total, 0)
                    removed = scale_down(autoscaled_workers, removable)
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

        time.sleep(int(settings["autoscaler_poll_seconds"]))


if __name__ == "__main__":
    main()
