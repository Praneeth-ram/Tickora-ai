import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_PATH = Path(os.getenv("AUDIT_LOG_PATH", "logs/audit.log"))

def configure_audit_logger() -> None:
    logger = logging.getLogger("audit")
    if any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
        return
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        LOG_PATH, maxBytes=10_000_000, backupCount=10, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter('{"ts":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}')
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False