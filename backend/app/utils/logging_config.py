"""
Structured logging configuration for TechPulse AI.
All application code should import get_logger() from here.
Handles UTF-8 stream encoding across Windows and Linux environments.
"""

import logging
import sys
from app.config.settings import settings

# Ensure stdout and stderr support UTF-8 (emojis and unicode quotes on Windows)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def get_logger(name: str) -> logging.Logger:
    """Return a named logger configured for TechPulse AI."""
    logger = logging.getLogger(name)

    if logger.handlers:
        # Already configured — avoid duplicate handlers on re-import
        return logger

    level = logging.DEBUG if settings.DEBUG else logging.INFO
    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(fmt)
    logger.addHandler(handler)
    logger.propagate = False

    return logger
