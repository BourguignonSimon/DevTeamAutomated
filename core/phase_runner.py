from __future__ import annotations

import logging
import multiprocessing
import queue
from typing import Any, Callable, Tuple

log = logging.getLogger(__name__)


def _worker(fn: Callable[..., Any], args: Tuple[Any, ...], kwargs: dict, result_queue: multiprocessing.Queue) -> None:
    try:
        fn(*args, **kwargs)
        result_queue.put(("ok", None))
    except Exception as exc:  # pragma: no cover - exception path asserted via parent
        log.exception("Phase handler raised")
        result_queue.put(("error", repr(exc)))


def run_with_timeout(fn: Callable[..., Any], timeout_s: float, *args: Any, **kwargs: Any) -> Tuple[bool, str | None]:
    """Execute `fn` in an isolated process and enforce timeout.

    Returns (ok, reason). When the timeout is exceeded the child process is terminated
    to prevent late side-effects (such as publishing events after cancellation).
    """

    ctx = multiprocessing.get_context("spawn")
    result_queue: multiprocessing.Queue = ctx.Queue()
    proc = ctx.Process(target=_worker, args=(fn, args, kwargs, result_queue))
    proc.start()
    proc.join(timeout_s)

    if proc.is_alive():
        proc.terminate()
        proc.join()
        return False, "timeout"

    try:
        status, reason = result_queue.get_nowait()
    except queue.Empty:
        return False, "unknown"

    if status == "ok":
        return True, None
    return False, reason or "error"
