"""Structured logging configuration for RAIL."""

import logging
import sys
from typing import Any


class ContextFormatter(logging.Formatter):
    """Formatter with context support for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with extra context."""
        base = super().format(record)

        # Add context if available
        context = getattr(record, "context", None)
        if context:
            context_str = " ".join([f"{k}={v}" for k, v in context.items()])
            return f"{base} [{context_str}]"

        return base


def setup_logging(
    level: str = "INFO",
    log_file: str | None = None,
    format_str: str | None = None,
) -> None:
    """Configure logging with file/console handlers.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR).
        log_file: Optional file path for log output.
        format_str: Custom format string.
    """
    # Default format
    if format_str is None:
        format_str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    formatter = ContextFormatter(format_str)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Suppress noisy third-party loggers
    logging.getLogger("web3").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with name.

    Args:
        name: Logger name (typically __name__).

    Returns:
        Logger instance.
    """
    return logging.getLogger(name)


def log_with_context(
    logger: logging.Logger,
    level: int,
    message: str,
    context: dict[str, Any] | None = None,
) -> None:
    """Log message with optional context.

    Args:
        logger: Logger instance.
        level: Log level (logging.INFO, etc.).
        message: Log message.
        context: Optional key-value context dict.
    """
    if context:
        logger.log(level, message, extra={"context": context})
    else:
        logger.log(level, message)
