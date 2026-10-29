"""The harness: models propose, the harness owns shared state and commits.

Commit modes, following the TeamBench contrast in Heng (2026):
``blind`` applies proposals without checks (the baseline that overspends),
``visible`` checks but only records violations as warnings and still
applies (a live count that agents can see but nothing enforces), and
``enforce`` rejects any proposal with a violation, atomically.

The gluing check tests whether several local views agree on the facts
they share: views that disagree on an overlapping key do not glue into
one world, and the harness reports the disagreement instead of picking
one view silently. Alias resolution maps different names for the same
entity (``total_cost``, ``cost_total``, ``amount_due``) to one canonical
key before any check runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .budgets import BudgetExceeded, Ledger
from .invariants import BUILTIN_INVARIANTS, Violation
from .state import StaleVersionError, VersionedStore
from .units import Quantity


class CommitMode(str, Enum):
    BLIND = "blind"
    VISIBLE = "visible"
    ENFORCE = "enforce"


@dataclass
class Intent:
    kind: str  # "set" | "reserve" | "spend" | "delete"
    key: str = ""
    value: object = None
    amount: Quantity | None = None
    unit: str | None = None
    budget: str = ""
    expected_version: int | None = None
    reservation_id: int | None = None
    owner: str = ""
    canonical_key: str | None = None


@dataclass
class Proposal:
    worker_id: str
    intents: list
    scope: str = ""


@dataclass
class ProposalResult:
    accepted: bool
    violations: list
    applied: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)


@dataclass
class Harness:
    store: VersionedStore = field(default_factory=VersionedStore)
    ledger: Ledger = field(default_factory=Ledger)
    aliases: dict = field(default_factory=dict)  # alias -> canonical key
    invariants: list = field(default_factory=lambda: list(BUILTIN_INVARIANTS))
    audit: list = field(default_factory=list)

    # -- aliasing ---------------------------------------------------------
    def canonical(self, key: str) -> str:
        return self.aliases.get(key, key)

    def add_alias(self, alias: str, canonical: str):
        self.aliases[alias] = canonical

    def detect_alias_conflict(self, proposals) -> list:
        """Two proposals touching aliased names of one entity with
        different values do not glue; report each conflict."""
        seen = {}
        conflicts = []
        for proposal in proposals:
            for intent in proposal.intents:
                if intent.kind != "set":
                    continue
                canon = self.canonical(intent.key)
                if canon in seen and seen[canon][0] != intent.value:
                    conflicts.append({
                        "key": canon,
                        "first": seen[canon],
                        "second": (intent.value, proposal.worker_id),
                    })
                seen.setdefault(canon, (intent.value, proposal.worker_id))
        return conflicts

    # -- gluing -----------------------------------------------------------
    def glue_check(self, views: list) -> list:
        """Check that local views agree on every key they share.

        Returns a list of disagreements: each names the key, the values
        seen, and the views involved. An empty list means the views glue
        into one consistent world.
        """
        seen = {}
        disagreements = []
        for index, view in enumerate(views):
            for key, value in view.items():
                canon = self.canonical(key)
                if canon in seen and seen[canon][0] != value:
                    disagreements.append({
                        "key": canon,
                        "values": [seen[canon][0], value],
                        "views": [seen[canon][1], index],
                    })
                seen.setdefault(canon, (value, index))
        return disagreements

    # -- commit -----------------------------------------------------------
    def commit(self, proposal: Proposal, mode: CommitMode = CommitMode.ENFORCE) -> ProposalResult:
        # Canonicalise keys and amounts before any check runs. A
        # conversion that fails (incompatible dimensions) is left
        # unconverted so the unit_consistency invariant can report it
        # as a violation instead of raising here.
        for intent in proposal.intents:
            intent.canonical_key = self.canonical(intent.key)
            if intent.amount is not None and intent.unit is not None:
                try:
                    intent.amount = intent.amount.to(intent.unit)
                except Exception:
                    pass

        violations = []
        for invariant in self.invariants:
            violations.extend(invariant.check(self.store, self.ledger, proposal))

        # Alias conflicts across the intents of this one proposal.
        if self.detect_alias_conflict([proposal]):
            violations.append(Violation(
                "ALIAS_CONFLICT",
                "aliased keys for one entity carry different values",
                "aliasing"))

        if mode is CommitMode.BLIND:
            applied = self._apply(proposal, force=True)
            self._record(proposal, True, [], mode)
            return ProposalResult(True, [], applied)

        if violations and mode is CommitMode.VISIBLE:
            applied = self._apply(proposal, force=True)
            self._record(proposal, True, violations, mode)
            return ProposalResult(True, violations, applied, warnings=violations)

        if violations:
            self._record(proposal, False, violations, mode)
            return ProposalResult(False, violations)

        applied = self._apply(proposal)
        self._record(proposal, True, [], mode)
        return ProposalResult(True, [], applied)

    def _apply(self, proposal: Proposal, force: bool = False) -> dict:
        applied = {}
        reservations = []
        try:
            for intent in proposal.intents:
                key = intent.canonical_key or intent.key
                if intent.kind == "set":
                    fact = self.store.set(
                        key, intent.value, proposal.worker_id,
                        expected_version=intent.expected_version)
                    applied[key] = fact.version
                elif intent.kind == "reserve":
                    reservation = self.ledger.reserve(
                        intent.budget, intent.amount, proposal.worker_id, force=force)
                    reservations.append(reservation)
                    applied[f"reservation:{reservation.id}"] = reservation.amount.value
                elif intent.kind == "spend":
                    reservation = self.ledger.reserve(
                        intent.budget, intent.amount, proposal.worker_id, force=force)
                    self.ledger.commit(reservation)
                    applied[f"spent:{intent.budget}"] = intent.amount.canonical().value
                elif intent.kind == "delete":
                    self.store.delete(key, proposal.worker_id,
                                      expected_version=intent.expected_version)
                    applied[key] = "deleted"
                else:
                    raise ValueError(f"unknown intent kind: {intent.kind!r}")
        except (StaleVersionError, BudgetExceeded, KeyError, ValueError):
            # Blind/visible application must not leave half a proposal
            # reserved: release anything held so far, then re-raise so the
            # caller sees the failure instead of a silent partial commit.
            self.ledger.release_all(reservations)
            raise
        return applied

    def _record(self, proposal, accepted, violations, mode):
        self.audit.append({
            "seq": len(self.audit) + 1,
            "worker": proposal.worker_id,
            "scope": proposal.scope,
            "mode": mode.value,
            "accepted": accepted,
            "violations": [v.code for v in violations],
        })

    def audit_trail(self):
        return list(self.audit)
