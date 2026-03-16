#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[1/6] Backend compile check"
python3 -m compileall backend/app >/dev/null

echo "[2/6] Worker compile check"
python3 -m compileall worker/app >/dev/null

echo "[3/6] Frontend production build"
(cd frontend && npm run build >/dev/null)

echo "[4/6] Smoke tests"
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -p 'test_*.py' >/dev/null
PYTHONPATH=worker python3 -m unittest discover -s worker/tests -p 'test_*.py' >/dev/null
(cd frontend && npm run test:smoke >/dev/null)
python3 scripts/check-index-coverage.py >/dev/null

echo "[5/6] Docker Compose validation"
docker compose config >/dev/null

echo "[6/6] Required files"
test -f README.md
test -f LICENSE
test -f .env.example

echo "release-readiness: ok"
