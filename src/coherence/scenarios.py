"""Reproducible scenarios that measure the harness, not the workers.

Each scenario is seeded and returns plain dicts of measured numbers.
The numbers reported in the README are the outputs of
``scripts/run_scenarios.py`` over the seeds listed there — they are
simulation measurements, not the numbers from Heng (2026), which are
cited separately in docs/RESEARCH.md.
"""

from __future__ import annotations

import random

from .budgets import Budget, Ledger
from .harness import CommitMode, Harness, Intent, Proposal
from .state import VersionedStore
from .units import Quantity
from .workers import local_spender, revision_guesser, visible_spender


def _fresh_harness(cap=100.0, unit="calls") -> Harness:
    harness = Harness(store=VersionedStore(), ledger=Ledger())
    harness.ledger.add_budget(Budget("calls", Quantity(cap, unit)))
    return harness


def team_bench(seed: int, n_workers: int = 5, cap: float = 100.0,
               each_spend: float = 30.0, mode: CommitMode = CommitMode.ENFORCE) -> dict:
    """Five workers each spend 30 from a shared cap of 100.

    Locally every spend looks affordable; jointly they total 150.
    Only commit enforcement keeps the total within the cap.
    """
    harness = _fresh_harness(cap)
    accepted = 0
    rejected = 0
    for i in range(n_workers):
        worker_id = f"worker-{i}"
        if mode is CommitMode.VISIBLE:
            remaining = harness.ledger.budgets["calls"].remaining
            proposal = visible_spender(worker_id, each_spend, remaining)
        else:
            proposal = local_spender(worker_id, each_spend)
        result = harness.commit(proposal, mode=mode)
        if result.accepted:
            accepted += 1
        else:
            rejected += 1
    spent = harness.ledger.total_spent("calls").canonical().value
    return {
        "seed": seed, "mode": mode.value, "workers": n_workers,
        "cap": cap, "each_spend": each_spend,
        "accepted": accepted, "rejected": rejected,
        "total_spent": spent, "over_cap": spent > cap + 1e-9,
        "violations": [v for entry in harness.audit_trail() for v in entry["violations"]],
    }


def revision_benchmark(seed: int, n: int = 40, visible: bool = False) -> dict:
    """The deciding fact is visible or hidden.

    Options are three rate limits; only one is correct for the task.
    Hidden workers guess uniformly at random (chance = 1/3); visible
    workers read the authoritative fact from the harness store and
    answer correctly. This is the simulation analogue of the
    observation-aliasing boundary: no amount of local reasoning
    recovers a fact the worker cannot see.
    """
    rng = random.Random(seed)
    harness = Harness(store=VersionedStore(), ledger=Ledger())
    harness.store.set("rate_limit", 25, writer="harness", provenance="authoritative")
    options = [10, 25, 50]
    correct = 0
    for i in range(n):
        visible_fact = 25 if visible else None
        _, choice = revision_guesser(f"worker-{i}", options, rng, visible_fact)
        if choice == 25:
            correct += 1
    return {"seed": seed, "n": n, "visible": visible,
            "correct": correct, "accuracy": correct / n}


def silent_revert(seed: int) -> dict:
    """A stale snapshot checker vs a harness that re-reads current state.

    The store holds the current config. An external change silently
    reverts it. A checker holding the old snapshot reports the old
    value as current (score 0); the harness's ``verify_current`` reads
    the store at check time and reports the truth.
    """
    _ = seed  # deterministic by construction; seed kept for API symmetry
    store = VersionedStore()
    store.set("config_version", "v3", writer="harness")
    snapshot = store.snapshot()  # stale checker keeps this
    store.force_external_set("config_version", "v2")  # silent revert
    stale_checker_says_current = snapshot["config_version"][0] == store.value("config_version")
    # The stale checker believes v3 is current because its snapshot says so;
    # it never re-reads, so it scores 0 against ground truth (v2).
    stale_score = 1.0 if snapshot["config_version"][0] == "v2" else 0.0
    harness_score = 1.0 if store.verify_current("config_version", "v2") else 0.0
    return {"seed": seed, "stale_checker_score": stale_score,
            "harness_score": harness_score,
            "current_value": store.value("config_version"),
            "stale_checker_says_current": stale_checker_says_current}


def unit_overlap(seed: int) -> dict:
    """Two workers write the same length through different units and
    different alias names. The harness canonicalises both to metres
    and reports no conflict when the values agree, and a conflict
    when they disagree."""
    _ = seed
    harness = Harness(store=VersionedStore(), ledger=Ledger())
    harness.add_alias("length_cm", "length")
    harness.add_alias("length_m", "length")
    agreeing = harness.glue_check([
        {"length_cm": Quantity(250, "cm")},
        {"length_m": Quantity(2.5, "m")},
    ])
    # Quantities compare by canonical value, so 250 cm == 2.5 m glues.
    # The raw dict comparison above treats Quantity objects by value:
    # Quantity.__eq__ canonicalises, so no disagreement is reported.
    disagreeing = harness.glue_check([
        {"length_cm": Quantity(250, "cm")},
        {"length_m": Quantity(3.0, "m")},
    ])
    return {"seed": seed,
            "agreeing_views_disagreements": len(agreeing),
            "disagreeing_views_disagreements": len(disagreeing)}


def run_all(seeds=(0, 1, 2, 3, 4)) -> dict:
    """Run every scenario over the given seeds and aggregate."""
    team = {}
    for mode in (CommitMode.BLIND, CommitMode.VISIBLE, CommitMode.ENFORCE):
        runs = [team_bench(seed, mode=mode) for seed in seeds]
        team[mode.value] = {
            "runs": len(runs),
            "violating_runs": sum(1 for r in runs if r["over_cap"]),
            "mean_total_spent": sum(r["total_spent"] for r in runs) / len(runs),
            "mean_accepted": sum(r["accepted"] for r in runs) / len(runs),
            "per_seed": runs,
        }
    revision = {}
    for visible in (False, True):
        runs = [revision_benchmark(seed, visible=visible) for seed in (0, 1, 2)]
        revision["visible" if visible else "hidden"] = {
            "runs": len(runs),
            "mean_accuracy": sum(r["accuracy"] for r in runs) / len(runs),
            "per_seed": runs,
        }
    revert = [silent_revert(seed) for seed in seeds]
    overlap = [unit_overlap(seed) for seed in seeds]
    return {
        "team_bench": team,
        "revision": revision,
        "silent_revert": {
            "runs": len(revert),
            "mean_stale_checker_score": sum(r["stale_checker_score"] for r in revert) / len(revert),
            "mean_harness_score": sum(r["harness_score"] for r in revert) / len(revert),
        },
        "unit_overlap": {
            "runs": len(overlap),
            "agreeing_disagreements": sum(r["agreeing_views_disagreements"] for r in overlap),
            "disagreeing_disagreements": sum(r["disagreeing_views_disagreements"] for r in overlap),
        },
    }
