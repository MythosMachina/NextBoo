import logging
import os

from app.upload_pipeline import UploadPipelineService


def configure_logging(log_level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def main() -> None:
    log_level = os.getenv("LOG_LEVEL", "INFO")
    stage_name = os.getenv("UPLOAD_PIPELINE_STAGE", "scanning").strip().lower()
    configure_logging(log_level)
    UploadPipelineService(stage_name).run_forever()


if __name__ == "__main__":
    main()
