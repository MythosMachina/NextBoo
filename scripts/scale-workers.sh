#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <worker-count>" >&2
  exit 1
fi

COUNT="$1"
if ! [[ "$COUNT" =~ ^[0-9]+$ ]]; then
  echo "worker-count must be an integer" >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! docker compose ps backend >/dev/null 2>&1; then
  echo "Backend service is not available. Start the stack first with: docker compose up -d"
  exit 1
fi

echo "Disabling autoscaler so manual worker scaling remains stable..."
docker compose exec -T backend python - <<'PY'
from app.db.session import SessionLocal
from app.services.app_settings import update_autoscaler_settings

with SessionLocal() as db:
    update_autoscaler_settings(db, {"autoscaler_enabled": False})
PY

echo "Scaling worker service to ${COUNT} container(s)..."
docker compose up -d --scale worker="$COUNT" worker
echo "worker scale: ok"
