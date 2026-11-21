"""Tests for the state machine helper every app uses for its statuses."""

import pytest

from apps.core.exceptions import ConflictError
from apps.core.state_machine import IllegalTransitionError, StateMachine

DOOR = StateMachine(
    "door",
    {
        "closed": {"open", "locked"},
        "open": {"closed"},
        "locked": {"closed"},
    },
)


@pytest.mark.parametrize(
    ("current", "target"), [("closed", "open"), ("closed", "locked"), ("open", "closed")]
)
def test_a_listed_move_is_allowed(current: str, target: str) -> None:
    assert DOOR.can(current, target) is True
    DOOR.check(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [("open", "locked"), ("locked", "open"), ("open", "open"), ("closed", "ajar")],
)
def test_any_other_move_is_refused(current: str, target: str) -> None:
    assert DOOR.can(current, target) is False

    with pytest.raises(IllegalTransitionError) as error:
        DOOR.check(current, target)

    assert isinstance(error.value, ConflictError)
    assert (error.value.status_code, error.value.code) == (409, "illegal_transition")
    assert str(error.value) == f"A door cannot go from {current} to {target}."


def test_next_states_are_listed_in_order() -> None:
    assert DOOR.next_states("closed") == ["locked", "open"]
    assert DOOR.next_states("ajar") == []


def test_every_state_and_the_end_states() -> None:
    one_way = StateMachine("ticket", {"new": {"used"}})

    assert one_way.states == {"new", "used"}
    assert one_way.is_final("used") is True
    assert one_way.is_final("new") is False


def test_a_machine_that_leads_to_nowhere_is_a_mistake() -> None:
    with pytest.raises(ValueError, match="no moves"):
        StateMachine("empty", {})
