import pytest

from coherence.budgets import Budget, BudgetExceeded, Ledger
from coherence.units import Quantity


def _ledger():
    ledger = Ledger()
    ledger.add_budget(Budget("calls", Quantity(100, "calls")))
    ledger.add_budget(Budget("money", Quantity(50, "USD")))
    return ledger


def test_reserve_commit_release_accounting():
    ledger = _ledger()
    r = ledger.reserve("calls", Quantity(30, "calls"), "w1")
    assert ledger.budgets["calls"].remaining == Quantity(70, "calls")
    ledger.commit(r)
    assert ledger.total_spent("calls") == Quantity(30, "calls")
    assert ledger.budgets["calls"].remaining == Quantity(70, "calls")
    assert r.state == "committed"


def test_release_returns_funds_and_is_idempotent():
    ledger = _ledger()
    r = ledger.reserve("calls", Quantity(30, "calls"), "w1")
    ledger.release(r)
    ledger.release(r)
    assert ledger.budgets["calls"].remaining == Quantity(100, "calls")
    assert ledger.total_spent("calls").value == 0


def test_reserve_beyond_remaining_raises_and_changes_nothing():
    ledger = _ledger()
    with pytest.raises(BudgetExceeded):
        ledger.reserve("calls", Quantity(101, "calls"), "w1")
    assert ledger.budgets["calls"].remaining == Quantity(100, "calls")
    assert ledger.events == []


def test_commit_of_released_or_committed_reservation_raises():
    ledger = _ledger()
    r = ledger.reserve("calls", Quantity(10, "calls"), "w1")
    ledger.release(r)
    with pytest.raises(ValueError):
        ledger.commit(r)
    r2 = ledger.reserve("calls", Quantity(10, "calls"), "w1")
    ledger.commit(r2)
    with pytest.raises(ValueError):
        ledger.commit(r2)


def test_reserve_all_is_atomic():
    ledger = _ledger()
    with pytest.raises(BudgetExceeded):
        ledger.reserve_all([("calls", Quantity(10, "calls")),
                            ("money", Quantity(999, "USD"))], owner="w1")
    assert ledger.budgets["calls"].remaining == Quantity(100, "calls")
    assert ledger.budgets["money"].remaining == Quantity(50, "USD")
    reservations = ledger.reserve_all([("calls", Quantity(10, "calls")),
                                       ("money", Quantity(5, "USD"))], owner="w1")
    assert len(reservations) == 2
    assert ledger.budgets["calls"].remaining == Quantity(90, "calls")


def test_amounts_in_other_units_count_against_cap():
    ledger = _ledger()
    # Money budget: CAD 100 at the default 0.73 rate = USD 73 > cap 50.
    with pytest.raises(BudgetExceeded):
        ledger.reserve("money", Quantity(100, "CAD"), "w1")
    r = ledger.reserve("money", Quantity(50, "CAD"), "w1")
    ledger.commit(r)
    assert ledger.total_spent("money").value == pytest.approx(36.5)


def test_is_over_cap_and_events_recorded():
    ledger = _ledger()
    assert ledger.is_over_cap("calls") is False
    r = ledger.reserve("calls", Quantity(100, "calls"), "w1")
    ledger.commit(r)
    assert ledger.is_over_cap("calls") is False
    kinds = [e["event"] for e in ledger.events]
    assert kinds == ["reserve", "commit"]
    assert ledger.events[0]["id"] == r.id


def test_unknown_budget_raises_key_error():
    ledger = _ledger()
    with pytest.raises(KeyError):
        ledger.reserve("nope", Quantity(1, "calls"), "w1")
