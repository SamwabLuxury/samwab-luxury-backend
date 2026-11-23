"""One small helper for every status in the project.

Each object with a status (a piece's custody, an order, a listing) has exactly
one table of allowed moves, kept next to the model that owns it. Services ask
the table before they change a status, so no code path can skip a step::

    CUSTODY = StateMachine("piece's custody", {"with_owner": {"in_transit"}, ...})
    CUSTODY.check(piece.custody_status, "in_transit")   # raises if not allowed
"""

from collections.abc import Mapping, Set

from apps.platform.core.exceptions import ConflictError


class IllegalTransitionError(ConflictError):
    code = "illegal_transition"
    message = "This status change is not allowed."


class StateMachine:
    def __init__(self, name: str, moves: Mapping[str, Set[str]]) -> None:
        if not moves:
            raise ValueError(f"The {name} state machine has no moves.")
        self.name = name
        self._moves = {state: frozenset(targets) for state, targets in moves.items()}

    @property
    def states(self) -> set[str]:
        found = set(self._moves)
        for targets in self._moves.values():
            found |= targets
        return found

    def can(self, current: str, target: str) -> bool:
        return target in self._moves.get(current, frozenset())

    def check(self, current: str, target: str) -> None:
        """Raise ``IllegalTransitionError`` (HTTP 409) unless the move is allowed."""
        if not self.can(current, target):
            raise IllegalTransitionError(f"A {self.name} cannot go from {current} to {target}.")

    def next_states(self, current: str) -> list[str]:
        return sorted(self._moves.get(current, frozenset()))

    def is_final(self, state: str) -> bool:
        return not self._moves.get(state)
