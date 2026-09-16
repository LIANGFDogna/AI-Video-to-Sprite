"""Shared atomic folder publish: Windows occasionally refuses a rename while a handle closes."""
import time
from pathlib import Path


def publish_folder(staging, target, attempts=5, delay=0.2):
    staging, target = Path(staging), Path(target)
    for attempt in range(attempts):
        try:
            staging.rename(target)
            return target
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)
    return target
