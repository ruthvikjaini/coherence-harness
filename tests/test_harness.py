import pytest

from coherence.budgets import Budget, Ledger
from coherence.harness import CommitMode, Harness, Intent, Proposal
from coherence.state import VersionedStore
from coherence.units import Quantity


def _harness():
    harness = Harness(store=VersionedStore(), ledger=Ledger())
    harness.ledger.add_budget(Budget("calls", Quantity(100, "calls")))
    return harness


def _spend(worker, amount):
    return Proposal(worker, [Intent(kind="spend", key="work",
                                    amount=Quantity(amount, "calls"),
                                    unit="calls", budget="calls", owner=worker)])


def test_enforce_rejects_overspend_and_applies_nothing():
    harness = _harness()
    assert harness.commit(_spend("w1", 60)).accepted is True
    result = harness.commit(_spend("w2", 60))
    assert result.accepted is False
    assert any(v.code == "BUDGET_EXCEEDED" for v in result.violations)
    assert harness.ledger.total_spent("calls") == Quantity(60, "calls")


def test_blind_mode_overspends_and_records_no_violations():
    harness = _harness()
    assert harness.commit(_spend("w1", 60), mode=CommitMode.BLIND).accepted
    assert harness.commit(_spend("w2", 60), mode=CommitMode.BLIND).accepted
    assert harness.ledger.total_spent("calls") == Quantity(120, "calls")
    assert harness.ledger.is_over_cap("calls") is True


def test_visible_mode_applies_but_warns():
    harness = _harness()
    harness.commit(_spend("w1", 60), mode=CommitMode.VISIBLE)
    result = harness.commit(_spend("w2", 60), mode=CommitMode.VISIBLE)
    assert result.accepted is True
    assert result.warnings
    assert any(v.code == "BUDGET_EXCEEDED" for v in result.warnings)
    assert harness.ledger.total_spent("calls") == Quantity(120, "calls")


def test_stale_version_rejected_and_state_unchanged():
    harness = _harness()
    harness.store.set("cfg", "v1", writer="harness")
    proposal = Proposal("w1", [Intent(kind="set", key="cfg", value="v2",
                                      expected_version=0, owner="w1")])
    result = harness.commit(proposal)
    assert result.accepted is False
    assert any(v.code == "STALE_VERSION" for v in result.violations)
    assert harness.store.value("cfg") == "v1"


def test_conflicting_writes_in_one_proposal_rejected():
    harness = _harness()
    proposal = Proposal("w1", [
        Intent(kind="set", key="k", value=1, owner="w1"),
        Intent(kind="set", key="k", value=2, owner="w1"),
    ])
    result = harness.commit(proposal)
    assert result.accepted is False
    assert any(v.code == "CONFLICTING_WRITE" for v in result.violations)
    assert harness.store.get("k") is None


def test_same_value_twice_is_not_a_conflict():
    harness = _harness()
    proposal = Proposal("w1", [
        Intent(kind="set", key="k", value=1, owner="w1"),
        Intent(kind="set", key="k", value=1, owner="w1"),
    ])
    assert harness.commit(proposal).accepted is True
    assert harness.store.value("k") == 1


def test_double_spend_reservation_id_rejected():
    harness = _harness()
    proposal = Proposal("w1", [
        Intent(kind="reserve", key="", amount=Quantity(10, "calls"), unit="calls",
               budget="calls", reservation_id=7, owner="w1"),
        Intent(kind="reserve", key="", amount=Quantity(10, "calls"), unit="calls",
               budget="calls", reservation_id=7, owner="w1"),
    ])
    result = harness.commit(proposal)
    assert result.accepted is False
    assert any(v.code == "DOUBLE_SPEND" for v in result.violations)


def test_unit_mismatch_declared_unit_vs_amount_rejected():
    harness = _harness()
    proposal = Proposal("w1", [Intent(kind="spend", key="work",
                                      amount=Quantity(10, "m"), unit="calls",
                                      budget="calls", owner="w1")])
    result = harness.commit(proposal)
    assert result.accepted is False
    assert any(v.code == "UNIT_MISMATCH" for v in result.violations)


def test_unknown_budget_rejected():
    harness = _harness()
    proposal = Proposal("w1", [Intent(kind="spend", key="work",
                                      amount=Quantity(10, "calls"), unit="calls",
                                      budget="ghost", owner="w1")])
    result = harness.commit(proposal)
    assert result.accepted is False
    assert any(v.code == "UNKNOWN_BUDGET" for v in result.violations)


def test_amount_canonicalised_to_declared_unit_before_apply():
    harness = _harness()
    harness.ledger.add_budget(Budget("tokens", Quantity(1000, "tokens")))
    proposal = Proposal("w1", [Intent(kind="spend", key="work",
                                      amount=Quantity(1, "ktokens"), unit="tokens",
                                      budget="tokens", owner="w1")])
    assert harness.commit(proposal).accepted is True
    assert harness.ledger.total_spent("tokens") == Quantity(1000, "tokens")


def test_alias_conflict_detected_and_gluing():
    harness = _harness()
    harness.add_alias("total_cost", "cost")
    harness.add_alias("cost_total", "cost")
    proposals = [
        Proposal("w1", [Intent(kind="set", key="total_cost", value=10, owner="w1")]),
        Proposal("w2", [Intent(kind="set", key="cost_total", value=20, owner="w2")]),
    ]
    conflicts = harness.detect_alias_conflict(proposals)
    assert len(conflicts) == 1
    assert conflicts[0]["key"] == "cost"
    assert harness.glue_check([{"total_cost": 10}, {"cost_total": 20}])
    assert harness.glue_check([{"total_cost": 10}, {"cost_total": 10}]) == []


def test_glue_check_reports_disagreement_views():
    harness = _harness()
    disagreements = harness.glue_check([{"a": 1, "b": 2}, {"a": 1, "b": 3}])
    assert len(disagreements) == 1
    assert disagreements[0]["key"] == "b"
    assert disagreements[0]["views"] == [0, 1]


def test_audit_trail_records_accepted_and_rejected():
    harness = _harness()
    harness.commit(_spend("w1", 10))
    harness.commit(_spend("w2", 999))
    trail = harness.audit_trail()
    assert [t["accepted"] for t in trail] == [True, False]
    assert trail[1]["violations"] == ["BUDGET_EXCEEDED"]
    assert [t["seq"] for t in trail] == [1, 2]


def test_delete_intent_and_unknown_kind():
    harness = _harness()
    harness.store.set("k", 1, writer="h")
    result = harness.commit(Proposal("w1", [Intent(kind="delete", key="k", owner="w1")]))
    assert result.accepted is True
    assert harness.store.get("k") is None
    with pytest.raises(ValueError):
        harness.commit(Proposal("w1", [Intent(kind="explode", key="k", owner="w1")]),
                       mode=CommitMode.BLIND)
