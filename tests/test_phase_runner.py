import multiprocessing
import time

from core.phase_runner import run_with_timeout


def _slow_handler(out_q):
    time.sleep(1.0)
    out_q.put("late")


def _fast_handler(out_q):
    out_q.put("done")


def test_handler_timeout_prevents_late_side_effects():
    ctx = multiprocessing.get_context("spawn")
    queue: multiprocessing.Queue = ctx.Queue()

    ok, reason = run_with_timeout(_slow_handler, 0.2, queue)

    assert ok is False
    assert reason == "timeout"
    time.sleep(0.2)
    assert queue.empty()


def test_handler_success_executes():
    ctx = multiprocessing.get_context("spawn")
    queue: multiprocessing.Queue = ctx.Queue()

    ok, reason = run_with_timeout(_fast_handler, 1.0, queue)
    assert ok is True
    assert reason is None
    assert queue.get(timeout=1.0) == "done"
