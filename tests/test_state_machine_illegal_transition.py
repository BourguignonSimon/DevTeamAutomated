import pytest

from core.state_machine import BacklogStatus, IllegalTransition, assert_transition


def test_illegal_transition_raises_with_context():
    with pytest.raises(IllegalTransition) as excinfo:
        assert_transition(BacklogStatus.DONE, BacklogStatus.READY, item_id="item-1")

    err = excinfo.value
    assert err.item_id == "item-1"
    assert err.from_state == BacklogStatus.DONE
    assert err.to_state == BacklogStatus.READY
    assert BacklogStatus.DONE not in err.allowed_transitions
