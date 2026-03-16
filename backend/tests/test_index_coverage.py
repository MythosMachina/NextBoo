import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class IndexCoverageTestCase(unittest.TestCase):
    def test_critical_model_indexes_are_present(self) -> None:
        image_model = (ROOT / "app" / "models" / "image.py").read_text()
        tag_model = (ROOT / "app" / "models" / "tag.py").read_text()
        import_model = (ROOT / "app" / "models" / "import_job.py").read_text()

        self.assertIn('checksum_sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)', image_model)
        self.assertIn('perceptual_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)', image_model)
        self.assertIn('name_normalized: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)', tag_model)
        self.assertIn('status: Mapped[JobStatus] = mapped_column(', import_model)
        self.assertIn('import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("imports.id", ondelete="SET NULL"), nullable=True, index=True)', import_model)


if __name__ == "__main__":
    unittest.main()
