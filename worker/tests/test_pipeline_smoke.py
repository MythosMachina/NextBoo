import unittest
from pathlib import Path

class WorkerPipelineSmokeTests(unittest.TestCase):
    def test_worker_settings_defaults_present(self) -> None:
        settings_source = Path(__file__).resolve().parents[1] / "app" / "settings.py"
        content = settings_source.read_text(encoding="utf-8")
        self.assertIn('tagger_provider: str = Field(default="camie"', content)
        self.assertIn('worker_concurrency: int = Field(default=2', content)


if __name__ == "__main__":
    unittest.main()
