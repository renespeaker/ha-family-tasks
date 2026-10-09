"""The points ledger: every booking per person, persisted by the integration.

Kept free of Home Assistant imports so the bookkeeping rules can be tested on
their own.

An award carries a unique key chosen by the caller (the card uses list + task,
plus the round for rotating chores). Awarding the same key twice does nothing,
so several devices reporting the same checked-off task book it only once.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Kind = Literal["award", "redeem", "adjust"]


class InsufficientPoints(Exception):
    """A redemption costs more than the person has."""

    def __init__(self, person: str, balance: int, points: int) -> None:
        super().__init__(f"{person} has {balance} points, needs {points}")
        self.person = person
        self.balance = balance
        self.points = points


@dataclass(frozen=True)
class Booking:
    """One line in the ledger."""

    kind: Kind
    person: str
    points: int  # always as booked: award/adjust add it, redeem subtracts it
    label: str
    at: str  # ISO timestamp
    key: str | None = None  # awards only


@dataclass(frozen=True)
class Totals:
    """What a person has: earned (awards + adjustments), redeemed and the rest."""

    earned: int
    redeemed: int

    @property
    def balance(self) -> int:
        return self.earned - self.redeemed


@dataclass
class Ledger:
    """All bookings, oldest first."""

    bookings: list[Booking] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Ledger:
        if not data:
            return cls()
        return cls([Booking(**b) for b in data.get("bookings", [])])

    def as_dict(self) -> dict[str, Any]:
        return {"bookings": [asdict(b) for b in self.bookings]}

    def _award_index(self, key: str) -> int | None:
        for i, b in enumerate(self.bookings):
            if b.kind == "award" and b.key == key:
                return i
        return None

    def award(self, key: str, person: str, points: int, label: str, at: str) -> bool:
        """Book points for a task. False when this key was already booked."""
        if points < 0:
            raise ValueError("award points must not be negative")
        if self._award_index(key) is not None:
            return False
        self.bookings.append(Booking("award", person, points, label, at, key))
        return True

    def revoke(self, key: str) -> Booking | None:
        """Take an award back (task unchecked). Returns what was removed."""
        i = self._award_index(key)
        return self.bookings.pop(i) if i is not None else None

    def redeem(self, person: str, points: int, label: str, at: str) -> None:
        """Spend points on a reward; refuses to go below zero."""
        if points <= 0:
            raise ValueError("redeem points must be positive")
        balance = self.totals(person).balance
        if points > balance:
            raise InsufficientPoints(person, balance, points)
        self.bookings.append(Booking("redeem", person, points, label, at))

    def adjust(self, person: str, points: int, label: str, at: str) -> None:
        """Bonus (positive) or deduction (negative) by a parent."""
        if points == 0:
            raise ValueError("adjust points must not be zero")
        self.bookings.append(Booking("adjust", person, points, label, at))

    def totals(self, person: str) -> Totals:
        earned = sum(b.points for b in self.bookings if b.person == person and b.kind != "redeem")
        redeemed = sum(b.points for b in self.bookings if b.person == person and b.kind == "redeem")
        return Totals(earned, redeemed)

    def last(self, person: str) -> Booking | None:
        for b in reversed(self.bookings):
            if b.person == person:
                return b
        return None

    def persons(self) -> list[str]:
        """Everyone with at least one booking, in first-seen order."""
        seen: dict[str, None] = {}
        for b in self.bookings:
            seen.setdefault(b.person, None)
        return list(seen)
