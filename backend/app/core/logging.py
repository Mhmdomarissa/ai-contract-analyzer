import logging
import sys

DEFAULT_LOG_LEVEL = logging.INFO


def configure_logging(level: int | str = DEFAULT_LOG_LEVEL) -> None:
    """Idempotent logging configuration for the app."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


configure_logging()

