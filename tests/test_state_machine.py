from core.state_machine import BacklogStatus, assert_transition


def test_illegal_transition_fails():
    res = assert_transition(BacklogStatus.READY, BacklogStatus.DONE)
    assert not res.ok
    assert "Illegal transition" in (res.reason or "")


def test_legal_transition_ok():
    res = assert_transition(BacklogStatus.READY, BacklogStatus.IN_PROGRESS)
    assert res.ok
