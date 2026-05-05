"""
utils/logger.py
Coloured console + rotating file logger.
"""
import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler

try:
    import colorlog
    HAS_COLOR = True
except ImportError:
    HAS_COLOR = False

LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(LOG_DIR, exist_ok=True)

def get_logger(name: str = "FyersBot", level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # ── Console handler ────────────────────────────────────────────────────────
    if HAS_COLOR:
        fmt = colorlog.ColoredFormatter(
            "%(log_color)s%(asctime)s [%(levelname)-8s]%(reset)s %(message)s",
            datefmt="%H:%M:%S",
            log_colors={
                "DEBUG":    "cyan",
                "INFO":     "green",
                "WARNING":  "yellow",
                "ERROR":    "red",
                "CRITICAL": "bold_red",
            },
        )
    else:
        fmt = logging.Formatter("%(asctime)s [%(levelname)-8s] %(message)s", datefmt="%H:%M:%S")

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # ── File handler ───────────────────────────────────────────────────────────
    today = datetime.now().strftime("%Y-%m-%d")
    fh = RotatingFileHandler(
        os.path.join(LOG_DIR, f"bot_{today}.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=7,
    )
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)-8s] %(message)s"))
    logger.addHandler(fh)

    return logger