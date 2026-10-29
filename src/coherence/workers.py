"""Deterministic simulated workers.

No worker calls an LLM. Each worker is a small policy over the local
view it is given, so the harness — not worker cleverness — is what is
being measured. All randomness comes from a seeded ``random.Random``,
so every scenario is reproducible from its seed.
"""

from __future__ import annotations

import random

from .harness import Intent, Proposal
from .units import Quantity


def local_spender(worker_id, spend, budget="calls", unit="calls"):
    """Spends from its own view only; never checks the shared ledger."""
    return Proposal(worker_id, [Intent(
        kind="spend", key="work", amount=Quantity(spend, unit),
        unit=unit, budget=budget, owner=worker_id)], scope="team-budget")


def visible_spender(worker_id, spend, remaining, budget="calls", unit="calls"):
    """Sees the live remaining count and spends anyway if it wants to.

    Seeing the count is not enforcement: in ``visible`` mode the
    harness warns but still applies, so this worker still overspends.
    """
    _ = remaining  # visible, but not binding
    return local_spender(worker_id, spend, budget, unit)


def unit_confused_writer(worker_id, key, value, unit, budget=None):
    """Writes a length in one unit where the shared state uses another.

    The harness canonicalises, so 250 cm and 2.5 m are the same fact;
    a checker that compares raw numbers would call them a conflict.
    """
    return Proposal(worker_id, [Intent(
        kind="set", key=key, value=value, owner=worker_id)], scope="units")


def stale_writer(worker_id, key, value, stale_version):
    """Writes from a snapshot taken before another worker's update."""
    return Proposal(worker_id, [Intent(
        kind="set", key=key, value=value,
        expected_version=stale_version, owner=worker_id)], scope="revision")


def revision_guesser(worker_id, options, rng: random.Random, visible_fact=None):
    """Decides a revision question. With the deciding fact visible it
    answers correctly; hidden, it picks uniformly at random among the
    options — chance performance, as the impossibility result predicts."""
    if visible_fact is not None:
        choice = visible_fact
    else:
        choice = rng.choice(options)
    return Proposal(worker_id, [Intent(
        kind="set", key="decision", value=choice, owner=worker_id)],
        scope="revision"), choice


def alias_writer(worker_id, alias_key, value):
    """Writes through an alias name for a shared entity."""
    return Proposal(worker_id, [Intent(
        kind="set", key=alias_key, value=value, owner=worker_id)],
        scope="aliases")
