"""Money as whole minor units (US cents) plus a currency code.

We never use floats or decimals for money. $12.50 is ``Money(1250)``.
A ``Money`` value cannot be changed after it is made, and it cannot be negative.
"""

from collections.abc import Sequence
from dataclasses import dataclass

DEFAULT_CURRENCY = "USD"
SUPPORTED_CURRENCIES = frozenset({"USD"})

# Rates are stored in basis points: 10,000 bps = 100%, so 25% = 2,500 bps.
BPS_DENOMINATOR = 10_000


class MoneyError(ValueError):
    """Raised when a money value or a money calculation is not allowed."""


class CurrencyMismatchError(MoneyError):
    """Raised when two amounts in different currencies are combined or compared."""


@dataclass(frozen=True, slots=True)
class Money:
    amount_minor: int
    currency: str = DEFAULT_CURRENCY

    def __post_init__(self) -> None:
        # bool is a kind of int in Python, so it must be refused by name.
        if isinstance(self.amount_minor, bool) or not isinstance(self.amount_minor, int):
            raise MoneyError("amount_minor must be a whole number of minor units (cents).")
        if self.amount_minor < 0:
            raise MoneyError("Money cannot be negative.")
        if self.currency not in SUPPORTED_CURRENCIES:
            raise MoneyError(f"Unsupported currency: {self.currency!r}.")

    @classmethod
    def zero(cls, currency: str = DEFAULT_CURRENCY) -> "Money":
        return cls(0, currency)

    def _require_same_currency(self, other: "Money") -> None:
        if not isinstance(other, Money):
            raise MoneyError("Money can only be combined or compared with Money.")
        if other.currency != self.currency:
            raise CurrencyMismatchError(f"Cannot mix {self.currency} with {other.currency}.")

    def __add__(self, other: "Money") -> "Money":
        self._require_same_currency(other)
        return Money(self.amount_minor + other.amount_minor, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._require_same_currency(other)
        if other.amount_minor > self.amount_minor:
            raise MoneyError("The result would be negative.")
        return Money(self.amount_minor - other.amount_minor, self.currency)

    def __lt__(self, other: "Money") -> bool:
        self._require_same_currency(other)
        return self.amount_minor < other.amount_minor

    def __le__(self, other: "Money") -> bool:
        self._require_same_currency(other)
        return self.amount_minor <= other.amount_minor

    def __gt__(self, other: "Money") -> bool:
        self._require_same_currency(other)
        return self.amount_minor > other.amount_minor

    def __ge__(self, other: "Money") -> bool:
        self._require_same_currency(other)
        return self.amount_minor >= other.amount_minor

    def share(self, bps: int) -> "Money":
        """Return a percentage of this amount. ``bps`` is basis points: 2,500 = 25%.

        Half a cent or more rounds up: 25% of $0.10 is 2.5 cents, which becomes 3.
        """
        if isinstance(bps, bool) or not isinstance(bps, int):
            raise MoneyError("bps must be a whole number.")
        if not 0 <= bps <= BPS_DENOMINATOR:
            raise MoneyError("bps must be between 0 and 10,000.")
        rounded = (self.amount_minor * bps + BPS_DENOMINATOR // 2) // BPS_DENOMINATOR
        return Money(rounded, self.currency)

    def split(self, weights: Sequence[int]) -> list["Money"]:
        """Split this amount in proportion to ``weights``. No cent is lost or invented.

        Every part is rounded down except the last, which takes what is left,
        so the parts always add up to the original amount.
        """
        if len(weights) == 0:
            raise MoneyError("split needs at least one weight.")
        for weight in weights:
            if isinstance(weight, bool) or not isinstance(weight, int) or weight < 0:
                raise MoneyError("Weights must be whole numbers, zero or more.")
        total_weight = sum(weights)
        if total_weight == 0:
            raise MoneyError("At least one weight must be more than zero.")

        parts = [self.amount_minor * weight // total_weight for weight in weights[:-1]]
        parts.append(self.amount_minor - sum(parts))
        return [Money(part, self.currency) for part in parts]

    def __str__(self) -> str:
        return f"{self.amount_minor // 100}.{self.amount_minor % 100:02d} {self.currency}"
