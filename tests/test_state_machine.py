import pytest

from core.state_machine import BacklogStatus, assert_transition


def test_illegal_transition_fails():
    with pytest.raises(ValueError):
        assert_transition(BacklogStatus.READY, BacklogStatus.DONE)


def test_legal_transition_ok():
    res = assert_transition(BacklogStatus.READY, BacklogStatus.IN_PROGRESS)
    assert res.ok


def test_in_progress_cannot_jump_backwards():
    with pytest.raises(ValueError):
        assert_transition(BacklogStatus.IN_PROGRESS, BacklogStatus.READY)
