#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_ROOT="${1:-$ROOT_DIR/backups/$TIMESTAMP}"
mkdir -p "$BACKUP_ROOT"

source .env 2>/dev/null || true
GALLERY_ROOT="${GALLERY_ROOT:-./gallery}"
POSTGRES_USER="${POSTGRES_USER:-nextboo}"
POSTGRES_DB="${POSTGRES_DB:-nextboo}"

echo "Creating backup under $BACKUP_ROOT"
mkdir -p "$BACKUP_ROOT/database" "$BACKUP_ROOT/storage"

if [ -f .env ]; then
  cp .env "$BACKUP_ROOT/.env.backup"
fi

docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > "$BACKUP_ROOT/database/nextboo.sql"

for path in content content_thumbs models imports queue processing processing_failed; do
  if [ -d "$GALLERY_ROOT/$path" ]; then
    tar -C "$GALLERY_ROOT" -cf "$BACKUP_ROOT/storage/${path}.tar" "$path"
  fi
done

echo "backup: ok"
