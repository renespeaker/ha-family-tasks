"""The bookkeeping rules, without Home Assistant."""

import pytest

from custom_components.family_tasks.ledger import InsufficientPoints, Ledger

T = "2026-10-09T10:00:00+00:00"


def test_award_books_once_per_key():
    led = Ledger()
    assert led.award("todo.lina|a1", "Lina", 10, "Tidy room", T)
    assert not led.award("todo.lina|a1", "Lina", 10, "Tidy room", T)  # second device
    assert led.totals("Lina").earned == 10


def test_revoke_takes_an_award_back():
    led = Ledger()
    led.award("k", "Lina", 10, "Tidy room", T)
    assert led.revoke("k").points == 10
    assert led.totals("Lina").earned == 0
    assert led.revoke("k") is None
    # and it can be earned again afterwards
    assert led.award("k", "Lina", 10, "Tidy room", T)


def test_redeem_spends_and_never_goes_below_zero():
    led = Ledger()
    led.award("k", "Lina", 30, "", T)
    led.redeem("Lina", 20, "Ice cream", T)
    assert (led.totals("Lina").balance, led.totals("Lina").redeemed) == (10, 20)
    with pytest.raises(InsufficientPoints) as err:
        led.redeem("Lina", 11, "Tablet", T)
    assert err.value.balance == 10
    assert led.totals("Lina").balance == 10


def test_adjust_adds_bonus_and_deduction_to_earned():
    led = Ledger()
    led.adjust("Ben", 20, "Helped", T)
    led.adjust("Ben", -5, "Fought", T)
    assert led.totals("Ben").earned == 15
    with pytest.raises(ValueError):
        led.adjust("Ben", 0, "", T)


def test_people_are_kept_apart():
    led = Ledger()
    led.award("a", "Lina", 10, "", T)
    led.award("b", "Ben", 5, "", T)
    assert (led.totals("Lina").balance, led.totals("Ben").balance) == (10, 5)
    assert led.persons() == ["Lina", "Ben"]


def test_survives_a_round_trip_through_storage():
    led = Ledger()
    led.award("a", "Lina", 10, "Bins", T)
    led.redeem("Lina", 4, "Sticker", T)
    again = Ledger.from_dict(led.as_dict())
    assert again == led
    assert not again.award("a", "Lina", 10, "Bins", T)


def test_rejects_nonsense():
    led = Ledger()
    with pytest.raises(ValueError):
        led.award("a", "Lina", -1, "", T)
    with pytest.raises(ValueError):
        led.redeem("Lina", 0, "", T)
