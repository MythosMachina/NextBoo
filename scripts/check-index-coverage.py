from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


CHECKS = {
    ROOT / "backend" / "app" / "models" / "image.py": [
        'checksum_sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)',
        'perceptual_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)',
    ],
    ROOT / "backend" / "app" / "models" / "tag.py": [
        'name_normalized: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)',
    ],
    ROOT / "backend" / "app" / "models" / "import_job.py": [
        'status: Mapped[JobStatus] = mapped_column(',
        'import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("imports.id", ondelete="SET NULL"), nullable=True, index=True)',
    ],
}


def main() -> None:
    missing: list[str] = []
    for file_path, needles in CHECKS.items():
        content = file_path.read_text()
        for needle in needles:
            if needle not in content:
                missing.append(f"{file_path.name}: {needle}")
    if missing:
        raise SystemExit("missing expected index markers:\n" + "\n".join(missing))


if __name__ == "__main__":
    main()
