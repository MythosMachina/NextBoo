#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "usage: $0 <backup-dir>"
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BACKUP_ROOT="$1"
source .env 2>/dev/null || true
GALLERY_ROOT="${GALLERY_ROOT:-./gallery}"
POSTGRES_USER="${POSTGRES_USER:-nextboo}"
POSTGRES_DB="${POSTGRES_DB:-nextboo}"

if [ ! -f "$BACKUP_ROOT/database/nextboo.sql" ]; then
  echo "missing database dump in $BACKUP_ROOT"
  exit 1
fi

printf "Restore backup from '%s'? Type YES to continue: " "$BACKUP_ROOT"
read -r CONFIRM
if [ "$CONFIRM" != "YES" ]; then
  echo "Aborted."
  exit 1
fi

echo "Stopping application services"
docker compose stop frontend backend worker worker_autoscaler >/dev/null 2>&1 || true

echo "Restoring database"
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" < "$BACKUP_ROOT/database/nextboo.sql"

mkdir -p "$GALLERY_ROOT"
for archive in "$BACKUP_ROOT"/storage/*.tar; do
  [ -e "$archive" ] || continue
  target_name="$(basename "$archive" .tar)"
  rm -rf "$GALLERY_ROOT/$target_name"
  tar -C "$GALLERY_ROOT" -xf "$archive"
done

if [ -f "$BACKUP_ROOT/.env.backup" ]; then
  cp "$BACKUP_ROOT/.env.backup" .env
fi

echo "Starting application services"
docker compose up -d frontend backend worker worker_autoscaler

echo "restore: ok"
