"""Commit-time coherence harness for multi-agent workflows.

Models propose; the harness owns shared state and governs commit.
"""

from .units import Quantity, UnitError, DimensionMismatch, parse_quantity, convert
from .state import VersionedStore, StaleVersionError, Fact
from .budgets import Budget, BudgetExceeded, Ledger
from .invariants import Invariant, Violation, BUILTIN_INVARIANTS
from .harness import Harness, Intent, Proposal, ProposalResult, CommitMode
from .escalation import EffortLevel, EscalationPolicy, run_comparison

__all__ = [
    "Quantity",
    "UnitError",
    "DimensionMismatch",
    "parse_quantity",
    "convert",
    "VersionedStore",
    "StaleVersionError",
    "Fact",
    "Budget",
    "BudgetExceeded",
    "Ledger",
    "Invariant",
    "Violation",
    "BUILTIN_INVARIANTS",
    "Harness",
    "Intent",
    "Proposal",
    "ProposalResult",
    "CommitMode",
    "EffortLevel",
    "EscalationPolicy",
    "run_comparison",
]
