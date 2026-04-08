"""
util/logger.py — Tilt Trial Arena / Mission Breach
Centralised logging: file + console.  Call setup_logger() once at startup,
then get_logger(name) anywhere in the project.
"""

import logging
import os
from datetime import datetime

_LOG_DIR = "logs"
_INITIALIZED = False


def setup_logger(name: str = "tilt_arena", level: int = logging.DEBUG) -> logging.Logger:
    """
    Configure root-level logging.  Creates a timestamped log file in logs/
    and a colour-free console handler.  Safe to call multiple times.
    """
    global _INITIALIZED
    if _INITIALIZED:
        return logging.getLogger(name)

    os.makedirs(_LOG_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(_LOG_DIR, f"{name}_{timestamp}.log")

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s  %(name)-20s  %(message)s",
        datefmt="%H:%M:%S",
    )

    # ── File handler (DEBUG and above) ─────────────────────────────────────
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # ── Console handler (INFO and above) ───────────────────────────────────
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    _INITIALIZED = True
    logger = logging.getLogger(name)
    logger.info(f"Logger started — writing to {log_file}")
    return logger


def get_logger(name: str) -> logging.Logger:
    """Return (or create) a named logger.  setup_logger() should be called first."""
    return logging.getLogger(name)
