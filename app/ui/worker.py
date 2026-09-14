from __future__ import annotations

import logging
import threading
import time

from PySide6.QtCore import QThread, Signal

from app.utils.ffmpeg import Cancelled

log = logging.getLogger("aivsprite.worker")


class Worker(QThread):
    progress = Signal(int, int, str)
    result = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, operation, parent=None):
        super().__init__(parent)
        self.operation = operation
        self.cancel_event = threading.Event()

    def run(self):
        try:
            last_report = [0.0, ""]
            def report(value, total, message):
                now = time.monotonic()
                if now - last_report[0] >= 0.05 or message != last_report[1] or value == total:
                    self.progress.emit(value, total, message)
                    last_report[:] = [now, message]
            result = self.operation(report, self.cancel_event)
            if self.cancel_event.is_set():
                self.cancelled.emit()
            else:
                self.result.emit(result)
        except Cancelled:
            self.cancelled.emit()
        except Exception as error:
            log.exception("Background operation failed")
            self.failed.emit(str(error))

    def cancel(self):
        self.cancel_event.set()
