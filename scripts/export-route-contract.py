import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTES_DIR = ROOT / "backend" / "app" / "api" / "v1" / "routes"
SNAPSHOT_PATH = ROOT / "backend" / "route_contract.snapshot.json"

ROUTE_PATTERN = re.compile(r'@router\.(?:get|post|patch|put|delete)\("([^"]*)"')
PREFIX_PATTERN = re.compile(r'APIRouter\(prefix="([^"]*)"')


def collect_route_paths() -> list[str]:
    discovered: set[str] = set()
    for file_path in sorted(ROUTES_DIR.glob("*.py")):
        source = file_path.read_text()
        prefix_match = PREFIX_PATTERN.search(source)
        prefix = prefix_match.group(1) if prefix_match else ""
        for route_match in ROUTE_PATTERN.finditer(source):
            discovered.add(f"/api/v1{prefix}{route_match.group(1)}")
    return sorted(discovered)


def main() -> None:
    SNAPSHOT_PATH.write_text(json.dumps({"paths": collect_route_paths()}, indent=2))


if __name__ == "__main__":
    main()
