"""Runs service.run_job and create.create_document on worker threads so the window stays
responsive."""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QThread, Signal

from .. import create, service


class JobWorker(QObject):
    """Lives on its own QThread. Signals carry the Python objects as they are (Signal(object));
    Signal(dict) would turn them into a QVariantMap and reorder the keys."""

    event = Signal(object)    # every service event (dict)
    finished = Signal(object) # JobResult.to_dict()
    failed = Signal(str)      # the request itself was invalid

    def __init__(self, request: service.JobRequest):
        super().__init__()
        self.request = request
        self._cancel = threading.Event()

    def cancel(self) -> None:
        """Cooperative: the service stops at the next file, page or export boundary."""
        self._cancel.set()

    def run(self) -> None:
        try:
            result = service.run_job(self.request, on_event=self.event.emit,
                                     cancel=self._cancel.is_set)
        except Exception as exc:
            self.failed.emit(service.short(f"{type(exc).__name__}: {exc}"))
            return
        self.finished.emit(result.to_dict())


def start(request: service.JobRequest, parent=None) -> tuple[QThread, JobWorker]:
    """Create the thread and worker, wired so both clean themselves up when the job ends."""
    thread = QThread(parent)
    worker = JobWorker(request)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    return thread, worker


class CreateWorker(QObject):
    """One create_document call on its own QThread. The result dict holds paths, not text."""

    finished = Signal(object)  # CreateResult.to_dict()

    def __init__(self, request: create.CreateRequest):
        super().__init__()
        self.request = request

    def run(self) -> None:
        try:
            result = create.create_document(self.request).to_dict()
        except Exception as exc:  # the service reports bad requests itself; this is a real bug
            result = {"status": "failed", "outputs": [], "warnings": [],
                      "error_code": "internal_error", "error": type(exc).__name__}
        self.finished.emit(result)


def start_create(request: create.CreateRequest, parent=None) -> tuple[QThread, CreateWorker]:
    thread = QThread(parent)
    worker = CreateWorker(request)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    return thread, worker
