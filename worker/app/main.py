import logging

from app.queue import WorkerService
from app.settings import get_settings


def configure_logging(log_level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = logging.getLogger("worker")
    logger.info(
        "worker started env=%s redis=%s queue=%s tagger=%s",
        settings.app_env,
        settings.redis_dsn,
        settings.ingest_queue_name,
        settings.tagger_provider,
    )
    WorkerService().run_forever()


if __name__ == "__main__":
    main()
