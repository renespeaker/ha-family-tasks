"""The points ledger: every booking per person, persisted by the integration.

Kept free of Home Assistant imports so the bookkeeping rules can be tested on
their own.

An award carries a unique key chosen by the caller (the card uses list + task,
plus the round for rotating chores). Awarding the same key twice does nothing,
so several devices reporting the same checked-off task book it only once.

A reward request reserves its points until a parent approves (it becomes a
redemption) or denies it (the points are free again). Reserved points can't be
requested or redeemed a second time.
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
class Request:
    """A reward asked for, waiting for a parent."""

    id: str
    person: str
    points: int
    label: str
    at: str


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
    requests: list[Request] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Ledger:
        if not data:
            return cls()
        return cls(
            [Booking(**b) for b in data.get("bookings", [])],
            [Request(**r) for r in data.get("requests", [])],
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "bookings": [asdict(b) for b in self.bookings],
            "requests": [asdict(r) for r in self.requests],
        }

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
        available = self.available(person)
        if points > available:
            raise InsufficientPoints(person, available, points)
        self.bookings.append(Booking("redeem", person, points, label, at))

    def request(self, request_id: str, person: str, points: int, label: str, at: str) -> Request:
        """Ask for a reward: reserve its points until a parent decides."""
        if points <= 0:
            raise ValueError("request points must be positive")
        available = self.available(person)
        if points > available:
            raise InsufficientPoints(person, available, points)
        req = Request(request_id, person, points, label, at)
        self.requests.append(req)
        return req

    def _take_request(self, request_id: str) -> Request | None:
        for i, r in enumerate(self.requests):
            if r.id == request_id:
                return self.requests.pop(i)
        return None

    def approve(self, request_id: str, at: str) -> Request | None:
        """A parent said yes: the reserved points are spent."""
        req = self._take_request(request_id)
        if req:
            self.bookings.append(Booking("redeem", req.person, req.points, req.label, at))
        return req

    def deny(self, request_id: str) -> Request | None:
        """A parent said no: the reserved points are free again."""
        return self._take_request(request_id)

    def pending(self, person: str) -> list[Request]:
        return [r for r in self.requests if r.person == person]

    def reserved(self, person: str) -> int:
        return sum(r.points for r in self.pending(person))

    def available(self, person: str) -> int:
        """What can still be spent: balance minus points reserved by requests."""
        return self.totals(person).balance - self.reserved(person)

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
        for r in self.requests:
            seen.setdefault(r.person, None)
        return list(seen)
