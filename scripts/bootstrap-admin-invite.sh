#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT_DIR"

if ! docker compose ps backend >/dev/null 2>&1; then
  echo "Backend service is not available. Start the stack first with: docker compose up -d"
  exit 1
fi

ADMIN_COUNT="$(docker compose exec -T backend python -m app.cli.admin_access count-admins --plain)"
if [ "$ADMIN_COUNT" != "0" ]; then
  echo "Refusing bootstrap invite: active admin account already exists."
  exit 1
fi

CODE="$(docker compose exec -T backend python -m app.cli.admin_access bootstrap-invite)"

echo
echo "Bootstrap admin invite created."
echo "Redeem it at: http://localhost:13000/invite"
echo "Invite code: $CODE"
echo
