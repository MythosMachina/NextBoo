#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ -f .env ]; then
  # shellcheck disable=SC1091
  . ./.env
fi

FRONTEND_PORT="${FRONTEND_PORT:-13000}"

printf "Create emergency admin invite? Type YES to continue: "
read -r CONFIRM

if [ "$CONFIRM" != "YES" ]; then
  echo "Aborted."
  exit 1
fi

CODE="$(docker compose exec -T backend python -m app.cli.admin_access rescue-invite --force)"

echo
echo "Rescue admin invite created."
echo "Redeem it at: http://localhost:${FRONTEND_PORT}/invite"
echo "Invite code: $CODE"
echo
