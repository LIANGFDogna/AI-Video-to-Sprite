import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import os


def configure_logging(directory: Path | None = None) -> Path:
    directory = directory or Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "AI Video to Sprite" / "logs"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "app.log"
    logger = logging.getLogger("aivsprite")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = RotatingFileHandler(path, maxBytes=4_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
    return path
