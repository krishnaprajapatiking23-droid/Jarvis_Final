"""Background worker pool for the UI (deep-spec section 11).

Nothing the dashboard does may run on the GUI thread: telemetry sampling,
command dispatch and long kernel calls are submitted here and their results
are published back to the UI. Jobs carry a timeout so a hung call degrades to
TIMEOUT instead of freezing the window.
"""

import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

try:
    import queue as _queue
except Exception:  # pragma: no cover
    import Queue as _queue  # type: ignore

OK = "ok"
INVALID = "invalid_input"
NOT_FOUND = "not_found"
UNAVAILABLE = "UNAVAILABLE"

PENDING = "pending"
RUNNING = "running"
DONE = "done"
FAILED = "failed"
CANCELLED = "cancelled"
TIMEOUT = "timeout"

DEFAULT_WORKERS = 3
DEFAULT_TIMEOUT = 30.0
MAX_RESULTS = 500


def new_job_id() -> str:
    return "JOB-%s" % uuid.uuid4().hex[:10]


class Job:
    def __init__(self, job_id: str, name: str, fn: Callable,
                 args: Any, kwargs: Any, timeout: float) -> None:
        self.id = job_id
        self.name = name
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.timeout = timeout
        self.state = PENDING
        self.result: Any = None
        self.error: Optional[str] = None
        self.submitted = time.time()
        self.started: Optional[float] = None
        self.finished: Optional[float] = None
        self.cancelled = False
        self.done = threading.Event()

    def to_dict(self) -> Dict[str, Any]:
        duration = None
        if self.started is not None and self.finished is not None:
            duration = round((self.finished - self.started) * 1000.0, 2)
        return {"status": OK, "job": self.id, "name": self.name,
                "state": self.state, "result": self.result,
                "error": self.error, "submitted": self.submitted,
                "duration_ms": duration, "cancelled": self.cancelled}


class WorkerPool:
    capability = "ui_workers"

    def __init__(self, workers: int = DEFAULT_WORKERS,
                 default_timeout: float = DEFAULT_TIMEOUT) -> None:
        self.size = max(1, int(workers))
        self.default_timeout = float(default_timeout)
        self._queue: Any = _queue.Queue()
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.RLock()
        self._listeners: List[Callable[[Dict[str, Any]], None]] = []
        self._mailbox: List[Dict[str, Any]] = []
        self._running = True
        self.completed = 0
        self.failed = 0
        self.timed_out = 0
        self.cancelled = 0
        self._threads = [threading.Thread(target=self._loop, daemon=True,
                                          name="jarvis-ui-worker-%d" % i)
                         for i in range(self.size)]
        for thread in self._threads:
            thread.start()

    # ---- submission ----
    def submit(self, name: str, fn: Callable, *args: Any,
               timeout: Optional[float] = None, **kwargs: Any) -> Dict[str, Any]:
        if not self._running:
            return {"status": UNAVAILABLE,
                    "error": "worker pool has been shut down"}
        if not callable(fn):
            return {"status": INVALID, "error": "a callable is required"}
        job = Job(new_job_id(), str(name), fn, args, kwargs,
                  float(timeout if timeout is not None else self.default_timeout))
        with self._lock:
            self._jobs[job.id] = job
        self._queue.put(job.id)
        self._watch(job)
        return {"status": OK, "job": job.id, "name": job.name}

    def on_result(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        self._listeners.append(callback)

    # ---- execution ----
    def _loop(self) -> None:
        while True:
            try:
                job_id = self._queue.get(timeout=0.2)
            except Exception:
                if not self._running:
                    return
                continue
            if job_id is None:
                return
            with self._lock:
                job = self._jobs.get(job_id)
            if job is None:
                continue
            if job.cancelled:
                self._finish(job, CANCELLED, None, "cancelled before start")
                continue
            job.state = RUNNING
            job.started = time.time()
            try:
                result = job.fn(*job.args, **job.kwargs)
            except Exception as exc:
                self._finish(job, FAILED, None, str(exc))
                continue
            if job.cancelled:
                self._finish(job, CANCELLED, result, "cancelled while running")
            elif job.state == TIMEOUT:
                job.done.set()
            else:
                self._finish(job, DONE, result, None)

    def _watch(self, job: Job) -> None:
        def watchdog() -> None:
            if job.done.wait(job.timeout):
                return
            if job.state in (DONE, FAILED, CANCELLED, TIMEOUT):
                return
            self._finish(job, TIMEOUT, None,
                         "job timed out after %.2fs" % job.timeout)

        threading.Thread(target=watchdog, daemon=True,
                         name="jarvis-ui-timeout").start()

    def _finish(self, job: Job, state: str, result: Any,
                error: Optional[str]) -> None:
        with self._lock:
            if job.state in (DONE, FAILED, CANCELLED, TIMEOUT):
                return
            job.state = state
            job.result = result
            job.error = error
            job.finished = time.time()
            if state == DONE:
                self.completed += 1
            elif state == FAILED:
                self.failed += 1
            elif state == TIMEOUT:
                self.timed_out += 1
            elif state == CANCELLED:
                self.cancelled += 1
            payload = job.to_dict()
            self._mailbox.append(payload)
            if len(self._mailbox) > MAX_RESULTS:
                del self._mailbox[0:len(self._mailbox) - MAX_RESULTS]
        job.done.set()
        for listener in list(self._listeners):
            try:
                listener(dict(payload))
            except Exception:
                pass  # a broken UI listener must not kill the worker

    # ---- inspection / control ----
    def status(self, job_id: str) -> Dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            return {"status": NOT_FOUND, "job": job_id}
        return job.to_dict()

    def cancel(self, job_id: str) -> Dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            return {"status": NOT_FOUND, "job": job_id}
        if job.state in (DONE, FAILED, TIMEOUT):
            return {"status": OK, "job": job_id, "cancelled": False,
                    "state": job.state,
                    "note": "job already finished"}
        job.cancelled = True
        return {"status": OK, "job": job_id, "cancelled": True,
                "state": job.state}

    def wait(self, job_id: str, timeout: float = 30.0) -> Dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            return {"status": NOT_FOUND, "job": job_id}
        job.done.wait(timeout)
        return job.to_dict()

    def drain(self) -> List[Dict[str, Any]]:
        with self._lock:
            finished = list(self._mailbox)
            self._mailbox.clear()
        return finished

    def pending(self) -> int:
        with self._lock:
            return sum(1 for job in self._jobs.values()
                       if job.state in (PENDING, RUNNING))

    def health(self) -> Dict[str, Any]:
        with self._lock:
            return {"available": self._running, "status": OK, "workers": self.size,
                    "jobs": len(self._jobs), "pending": self.pending(),
                    "completed": self.completed, "failed": self.failed,
                    "timed_out": self.timed_out, "cancelled": self.cancelled,
                    "mailbox": len(self._mailbox)}

    def shutdown(self, timeout: float = 2.0) -> Dict[str, Any]:
        self._running = False
        for _ in self._threads:
            self._queue.put(None)
        alive = 0
        for thread in self._threads:
            thread.join(timeout)
            if thread.is_alive():
                alive += 1
        return {"status": OK, "stopped": alive == 0, "still_running": alive}
