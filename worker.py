from __future__ import annotations

import queue
import threading
from collections.abc import Callable

from PyObjCTools import AppHelper

from .models import JobProgress, JobRequest, JobResult
from .pipeline import SubtitlePipeline


ProgressHandler = Callable[[JobProgress], None]
CompletionHandler = Callable[[JobResult], None]
ErrorHandler = Callable[[JobRequest, Exception], None]
StateHandler = Callable[[bool, int], None]


class JobRunner:
    def __init__(
        self,
        on_progress: ProgressHandler,
        on_complete: CompletionHandler,
        on_error: ErrorHandler,
        on_state_changed: StateHandler,
    ) -> None:
        self.on_progress = on_progress
        self.on_complete = on_complete
        self.on_error = on_error
        self.on_state_changed = on_state_changed
        self.pipeline = SubtitlePipeline()
        self._queue: queue.Queue[JobRequest] = queue.Queue()
        self._lock = threading.Lock()
        self._active = False
        self._thread = threading.Thread(target=self._run, name="SubbeXJobRunner", daemon=True)
        self._thread.start()

    def enqueue(self, requests: list[JobRequest]) -> None:
        for request in requests:
            self._queue.put(request)
        self._dispatch_state()

    def is_busy(self) -> bool:
        with self._lock:
            return self._active or not self._queue.empty()

    def pending_count(self) -> int:
        return self._queue.qsize()

    def _run(self) -> None:
        while True:
            request = self._queue.get()
            with self._lock:
                self._active = True
            self._dispatch_state()

            try:
                result = self.pipeline.process_job(
                    request,
                    progress_callback=lambda phase, fraction, detail: self._dispatch_progress(
                        JobProgress(
                            phase=phase,
                            fraction=fraction,
                            detail=detail,
                            input_path=request.input_path,
                            queue_depth=self._queue.qsize(),
                        )
                    ),
                )
                AppHelper.callAfter(self.on_complete, result)
            except Exception as exc:
                AppHelper.callAfter(self.on_error, request, exc)
            finally:
                with self._lock:
                    self._active = False
                self._queue.task_done()
                self._dispatch_state()

    def _dispatch_progress(self, progress: JobProgress) -> None:
        AppHelper.callAfter(self.on_progress, progress)

    def _dispatch_state(self) -> None:
        busy = self.is_busy()
        queue_depth = self._queue.qsize()
        AppHelper.callAfter(self.on_state_changed, busy, queue_depth)

