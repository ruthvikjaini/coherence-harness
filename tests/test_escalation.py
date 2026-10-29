import pytest

from coherence.escalation import (
    EFFORT_LEVELS,
    EscalationPolicy,
    run_comparison,
    sample_tasks,
    verify,
)


def test_effort_levels_cost_ratio_is_42():
    costs = {lv.name: lv.cost_multiplier for lv in EFFORT_LEVELS}
    assert costs["low"] == 1.0
    assert costs["max"] == 42.0
    assert [lv.name for lv in EFFORT_LEVELS] == ["low", "medium", "high", "xhigh", "max"]
    assert list(costs.values()) == sorted(costs.values())


def test_sample_tasks_reproducible_for_same_seed():
    a = sample_tasks(50, seed=7)
    b = sample_tasks(50, seed=7)
    assert [(t.difficulty, t.solves) for t in a] == [(t.difficulty, t.solves) for t in b]
    c = sample_tasks(50, seed=8)
    assert [(t.difficulty, t.solves) for t in a] != [(t.difficulty, t.solves) for t in c]


def test_sample_tasks_always_have_at_least_one_solving_level():
    for task in sample_tasks(500, seed=1):
        assert task.solves
        assert task.solves <= {lv.name for lv in EFFORT_LEVELS}


def test_solving_sets_are_non_monotonic():
    tasks = sample_tasks(500, seed=3)
    non_monotonic = 0
    for task in tasks:
        solved = [lv.name in task.solves for lv in EFFORT_LEVELS]
        # A higher level failing while a cheaper level succeeds.
        if any(solved[i] and not solved[j] for i in range(len(solved)) for j in range(i + 1, len(solved))):
            non_monotonic += 1
    assert non_monotonic > 0, "simulation must include higher-effort failures"


def test_verify_matches_solving_set():
    task = sample_tasks(1, seed=0)[0]
    for level in EFFORT_LEVELS:
        assert verify(task, level.name) == (level.name in task.solves)


def test_escalate_stops_at_first_verified_pass_and_never_exceeds_max_cost():
    tasks = sample_tasks(100, seed=2)
    policy = EscalationPolicy("escalate")
    for task in tasks:
        outcome = policy.run_task(task)
        assert outcome["cost"] <= sum(lv.cost_multiplier for lv in EFFORT_LEVELS)
        assert outcome["attempts"] <= len(EFFORT_LEVELS)
        assert outcome["success"] is True  # every task has a solving level


def test_fixed_policies_pay_one_level_only():
    task = sample_tasks(1, seed=0)[0]
    assert EscalationPolicy("fixed_low").run_task(task)["cost"] == 1.0
    assert EscalationPolicy("fixed_max").run_task(task)["cost"] == 42.0
    assert EscalationPolicy("oracle").run_task(task)["success"] is True


def test_unknown_policy_rejected():
    with pytest.raises(ValueError):
        EscalationPolicy("always_max")


def test_comparison_escalate_beats_fixed_max_on_cost_and_success():
    result = run_comparison(n_tasks=200, seed=0)
    assert result["escalate"]["success_rate"] >= result["fixed_max"]["success_rate"]
    assert result["escalate"]["total_cost"] < result["fixed_max"]["total_cost"]
    assert result["oracle"]["total_cost"] <= result["escalate"]["total_cost"]
    assert result["fixed_max"]["total_cost"] == 200 * 42.0
    assert result["seed"] == 0


def test_comparison_reproducible_and_cost_per_success_consistent():
    a = run_comparison(200, seed=42)
    b = run_comparison(200, seed=42)
    assert a == b
    for name, row in a.items():
        if isinstance(row, dict) and row["successes"]:
            assert row["cost_per_success"] == pytest.approx(row["total_cost"] / row["successes"])
