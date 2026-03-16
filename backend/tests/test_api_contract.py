import json
import re
import unittest
from pathlib import Path


ROUTES_DIR = Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "routes"
SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / "route_contract.snapshot.json"


ROUTE_PATTERN = re.compile(r'@router\.(?:get|post|patch|put|delete)\("([^"]*)"')
PREFIX_PATTERN = re.compile(r'APIRouter\(prefix="([^"]*)"')


def collect_route_paths() -> set[str]:
    discovered: set[str] = set()
    for file_path in sorted(ROUTES_DIR.glob("*.py")):
        source = file_path.read_text()
        prefix_match = PREFIX_PATTERN.search(source)
        prefix = prefix_match.group(1) if prefix_match else ""
        for route_match in ROUTE_PATTERN.finditer(source):
            route_path = route_match.group(1)
            discovered.add(f"/api/v1{prefix}{route_path}")
    return discovered


class ApiContractTestCase(unittest.TestCase):
    def test_critical_paths_exist(self) -> None:
        schema_paths = collect_route_paths()
        critical_paths = {
            "/api/v1/auth/login",
            "/api/v1/auth/refresh",
            "/api/v1/images",
            "/api/v1/images/{image_id}",
            "/api/v1/images/{image_id}/related",
            "/api/v1/search",
            "/api/v1/uploads",
            "/api/v1/uploads/import-folder",
            "/api/v1/uploads/import-zip",
            "/api/v1/uploads/import-sources",
            "/api/v1/moderation/near-duplicates",
            "/api/v1/admin/settings/rate-limits",
        }
        self.assertTrue(critical_paths.issubset(schema_paths))

    def test_route_snapshot_matches(self) -> None:
        current_paths = collect_route_paths()
        snapshot = json.loads(SNAPSHOT_PATH.read_text())
        self.assertEqual(set(snapshot["paths"]), current_paths)


if __name__ == "__main__":
    unittest.main()
