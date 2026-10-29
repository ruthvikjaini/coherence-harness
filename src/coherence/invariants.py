"""Invariants checked at commit time, before anything is applied.

An invariant is a named predicate over the current store, the ledger,
and the proposal being committed. All invariants run before any intent
is applied, so a rejected proposal changes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

from .units import DimensionMismatch  # noqa: F401  (re-exported for callers)


@dataclass
class Violation:
    code: str
    message: str
    invariant: str
    severity: str = "error"


@dataclass
class Invariant:
    name: str
    check: object  # callable(store, ledger, proposal) -> list[Violation]


def _budget_cap(store, ledger, proposal):
    violations = []
    totals = {}
    for intent in proposal.intents:
        if intent.kind in ("reserve", "spend") and intent.amount is not None:
            totals[intent.budget] = totals.get(intent.budget, 0.0) + intent.amount.canonical().value
    for budget_name, total in totals.items():
        budget = ledger.budgets.get(budget_name)
        if budget is None:
            violations.append(Violation("UNKNOWN_BUDGET", f"unknown budget {budget_name!r}", "budget_cap"))
            continue
        remaining = budget.remaining.canonical().value
        if total > remaining + 1e-9:
            violations.append(Violation(
                "BUDGET_EXCEEDED",
                f"proposal spends {total} of budget {budget_name!r} but only {remaining} remains",
                "budget_cap"))
    return violations


def _no_double_spend(store, ledger, proposal):
    seen = set()
    violations = []
    for intent in proposal.intents:
        if intent.reservation_id is not None:
            if intent.reservation_id in seen:
                violations.append(Violation(
                    "DOUBLE_SPEND",
                    f"reservation {intent.reservation_id} used twice in one proposal",
                    "no_double_spend"))
            seen.add(intent.reservation_id)
    return violations


def _unit_consistency(store, ledger, proposal):
    from .units import dimension_of

    violations = []
    for intent in proposal.intents:
        if intent.amount is not None and intent.unit is not None:
            try:
                declared = dimension_of(intent.unit)
            except Exception as exc:  # unknown unit
                violations.append(Violation("UNKNOWN_UNIT", str(exc), "unit_consistency"))
                continue
            if declared != intent.amount.dimension:
                violations.append(Violation(
                    "UNIT_MISMATCH",
                    f"intent for {intent.key!r} declares unit {intent.unit} "
                    f"but amount is in {intent.amount.unit}",
                    "unit_consistency"))
    return violations


def _no_conflicting_write(store, ledger, proposal):
    seen = {}
    violations = []
    for intent in proposal.intents:
        if intent.kind == "set":
            key = intent.canonical_key or intent.key
            if key in seen and seen[key] != intent.value:
                violations.append(Violation(
                    "CONFLICTING_WRITE",
                    f"key {key!r} is written with two different values in one proposal",
                    "no_conflicting_write"))
            seen[key] = intent.value
    return violations


def _version_freshness(store, ledger, proposal):
    violations = []
    for intent in proposal.intents:
        if intent.kind == "set" and intent.expected_version is not None:
            current = store.version(intent.canonical_key or intent.key)
            if intent.expected_version != current:
                violations.append(Violation(
                    "STALE_VERSION",
                    f"key {intent.key!r}: expected version {intent.expected_version}, "
                    f"current version is {current}",
                    "version_freshness"))
    return violations


BUILTIN_INVARIANTS = [
    Invariant("budget_cap", _budget_cap),
    Invariant("no_double_spend", _no_double_spend),
    Invariant("unit_consistency", _unit_consistency),
    Invariant("no_conflicting_write", _no_conflicting_write),
    Invariant("version_freshness", _version_freshness),
]

__all__ = ["Invariant", "Violation", "BUILTIN_INVARIANTS"]
