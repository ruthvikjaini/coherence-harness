"""Verified-failure-only effort escalation, after Sun et al. (2026).

Sun et al. found that the highest reasoning effort can cost up to 42x
the lowest on tasks every level solves, that higher effort frequently
fails tasks lower effort solved, and that starting low and escalating
only after a verified failure matches or improves on fixed maximum
effort at lower cost. This module implements that policy over simulated
tasks with a ground-truth verifier, so the comparison is measurable
without any API calls.

Task model (simulation, stated honestly): each task has a difficulty
and a set of effort levels that solve it, sampled with a seeded RNG.
The solving sets are deliberately non-monotonic — a higher level can
fail a task a lower level solves — matching the paper's finding. Cost
multipliers are parameters (low=1, max=42, geometric in between),
anchored to the paper's reported 42x ratio, not measured from a live
API. Do not quote this module's cost ratios as measurements of any
real model.
"""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class EffortLevel:
    name: str
    cost_multiplier: float


EFFORT_LEVELS = [
    EffortLevel("low", 1.0),
    EffortLevel("medium", 3.0),
    EffortLevel("high", 9.0),
    EffortLevel("xhigh", 21.0),
    EffortLevel("max", 42.0),
]


@dataclass
class Task:
    id: int
    difficulty: float  # 0 (easy) to 1 (hard)
    solves: frozenset  # effort-level names that solve this task


def sample_tasks(n: int, seed: int) -> list:
    """Sample tasks whose solving sets are non-monotonic in effort.

    Easy tasks are solved by every level. Harder tasks are solved by
    a random subset of levels biased toward higher effort, with a
    chance that a level fails even when a cheaper level succeeds.
    """
    rng = random.Random(seed)
    tasks = []
    for i in range(n):
        difficulty = rng.random()
        solves = set()
        for level in EFFORT_LEVELS:
            # Base success rises with effort and falls with difficulty,
            # with per-level noise so monotonicity is not guaranteed.
            p = max(0.0, min(1.0, 0.95 - difficulty * 0.7
                             + ({"low": -0.15, "medium": 0.0, "high": 0.1,
                                 "xhigh": 0.15, "max": 0.18}[level.name])
                             + rng.uniform(-0.12, 0.12)))
            if rng.random() < p:
                solves.add(level.name)
        if not solves:
            solves.add("max")
        tasks.append(Task(id=i, difficulty=difficulty, solves=frozenset(solves)))
    return tasks


def verify(task: Task, level_name: str) -> bool:
    """Ground-truth verifier: the attempt passes iff the level solves it."""
    return level_name in task.solves


class EscalationPolicy:
    """Policies for choosing effort. ``escalate`` starts at the lowest
    level and moves up only when the verifier reports failure."""

    def __init__(self, name: str):
        if name not in ("fixed_low", "fixed_max", "escalate", "oracle"):
            raise ValueError(f"unknown policy: {name!r}")
        self.name = name

    def run_task(self, task: Task) -> dict:
        """Return success and total cost multiplier for one task."""
        if self.name == "fixed_low":
            level = EFFORT_LEVELS[0]
            return {"success": verify(task, level.name), "cost": level.cost_multiplier,
                    "attempts": 1}
        if self.name == "fixed_max":
            level = EFFORT_LEVELS[-1]
            return {"success": verify(task, level.name), "cost": level.cost_multiplier,
                    "attempts": 1}
        if self.name == "oracle":
            solving = [lv for lv in EFFORT_LEVELS if lv.name in task.solves]
            cheapest = min(solving, key=lambda lv: lv.cost_multiplier)
            return {"success": True, "cost": cheapest.cost_multiplier, "attempts": 1}
        # escalate
        cost = 0.0
        attempts = 0
        for level in EFFORT_LEVELS:
            cost += level.cost_multiplier
            attempts += 1
            if verify(task, level.name):
                return {"success": True, "cost": cost, "attempts": attempts}
        return {"success": False, "cost": cost, "attempts": attempts}


def run_comparison(n_tasks: int = 200, seed: int = 0) -> dict:
    """Compare the four policies on the same sampled tasks."""
    tasks = sample_tasks(n_tasks, seed)
    results = {}
    for name in ("fixed_low", "fixed_max", "escalate", "oracle"):
        policy = EscalationPolicy(name)
        outcomes = [policy.run_task(task) for task in tasks]
        successes = sum(1 for o in outcomes if o["success"])
        total_cost = sum(o["cost"] for o in outcomes)
        results[name] = {
            "tasks": n_tasks,
            "successes": successes,
            "success_rate": successes / n_tasks,
            "total_cost": total_cost,
            "mean_cost_per_task": total_cost / n_tasks,
            "cost_per_success": total_cost / successes if successes else None,
            "mean_attempts": sum(o["attempts"] for o in outcomes) / n_tasks,
        }
    results["seed"] = seed
    results["cost_ratio_max_to_low"] = 42.0
    return results
