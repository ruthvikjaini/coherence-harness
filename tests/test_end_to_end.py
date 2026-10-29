"""End-to-end: scenarios, CLI, audit export, and the full pipeline."""

import json
import subprocess
import sys

import pytest

from coherence.audit import audit_summary, audit_to_jsonl
from coherence.cli import main as cli_main
from coherence.escalation import run_comparison
from coherence.harness import CommitMode, Harness
from coherence.scenarios import (
    revision_benchmark,
    run_all,
    silent_revert,
    team_bench,
    unit_overlap,
)


def test_team_bench_enforce_never_overspends_across_seeds():
    for seed in range(5):
        result = team_bench(seed, mode=CommitMode.ENFORCE)
        assert result["over_cap"] is False
        assert result["total_spent"] <= 100.0
        assert result["accepted"] == 3  # 3 x 30 = 90; the 4th would exceed 100


def test_team_bench_blind_and_visible_overspend_every_run():
    for mode in (CommitMode.BLIND, CommitMode.VISIBLE):
        for seed in range(5):
            result = team_bench(seed, mode=mode)
            assert result["over_cap"] is True
            assert result["total_spent"] == pytest.approx(150.0)


def test_revision_visible_is_perfect_and_hidden_is_near_chance():
    hidden = [revision_benchmark(seed, visible=False)["accuracy"] for seed in (0, 1, 2)]
    visible = [revision_benchmark(seed, visible=True)["accuracy"] for seed in (0, 1, 2)]
    assert visible == [1.0, 1.0, 1.0]
    mean_hidden = sum(hidden) / len(hidden)
    assert 0.15 <= mean_hidden <= 0.55, f"hidden mean {mean_hidden} should be near 1/3"


def test_silent_revert_harness_beats_stale_checker():
    result = silent_revert(0)
    assert result["harness_score"] == 1.0
    assert result["stale_checker_score"] == 0.0
    assert result["current_value"] == "v2"


def test_unit_overlap_gluing():
    result = unit_overlap(0)
    assert result["agreeing_views_disagreements"] == 0
    assert result["disagreeing_views_disagreements"] == 1


def test_run_all_aggregates_match_per_seed_runs():
    output = run_all(seeds=(0, 1))
    assert output["team_bench"]["enforce"]["runs"] == 2
    assert output["team_bench"]["enforce"]["violating_runs"] == 0
    assert output["team_bench"]["blind"]["violating_runs"] == 2
    assert output["revision"]["visible"]["mean_accuracy"] == 1.0
    assert output["silent_revert"]["mean_harness_score"] == 1.0


def test_cli_demo_exits_zero_and_reports_rejection(capsys):
    assert cli_main(["demo"]) == 0
    out = capsys.readouterr().out
    assert "accepted=False" in out
    assert "Total spent: 60.0 calls" in out


def test_cli_scenario_json_is_parseable(capsys):
    assert cli_main(["scenario", "team-bench", "--seed", "1"]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["total_spent"] == pytest.approx(90.0)


def test_cli_compare_json_is_parseable(capsys):
    assert cli_main(["compare", "--tasks", "20", "--seed", "0"]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["fixed_max"]["tasks"] == 20


def test_cli_audit_accepts_and_rejects_proposal_files(tmp_path, capsys):
    good = {"worker_id": "w1", "intents": [
        {"kind": "spend", "key": "work", "amount": 10, "unit": "calls", "budget": "calls"}]}
    bad = {"worker_id": "w1", "intents": [
        {"kind": "spend", "key": "work", "amount": 999, "unit": "calls", "budget": "calls"}]}
    good_path = tmp_path / "good.json"
    bad_path = tmp_path / "bad.json"
    good_path.write_text(json.dumps(good))
    bad_path.write_text(json.dumps(bad))
    assert cli_main(["audit", str(good_path)]) == 0
    assert json.loads(capsys.readouterr().out)["accepted"] is True
    assert cli_main(["audit", str(bad_path)]) == 0
    assert json.loads(capsys.readouterr().out)["accepted"] is False


def test_cli_as_subprocess_from_project_root():
    root = __file__.rsplit("/tests/", 1)[0]
    proc = subprocess.run(
        [sys.executable, "-m", "coherence.cli", "demo"],
        cwd=root, env={"PYTHONPATH": f"{root}/src", "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0
    assert "Total spent" in proc.stdout


def test_audit_export_round_trips():
    harness = Harness()
    harness.audit.append({"seq": 1, "worker": "w", "scope": "", "mode": "enforce",
                          "accepted": True, "violations": []})
    harness.audit.append({"seq": 2, "worker": "w", "scope": "", "mode": "enforce",
                          "accepted": False, "violations": ["BUDGET_EXCEEDED"]})
    lines = audit_to_jsonl(harness.audit_trail()).splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["violations"] == ["BUDGET_EXCEEDED"]
    summary = audit_summary(harness.audit_trail())
    assert summary == {"entries": 2, "accepted": 1, "rejected": 1,
                       "violations": {"BUDGET_EXCEEDED": 1}}


def test_full_pipeline_seed_0_matches_experiment_script_shape():
    comparison = run_comparison(200, seed=0)
    assert comparison["escalate"]["success_rate"] == 1.0
    assert comparison["escalate"]["total_cost"] < comparison["fixed_max"]["total_cost"]
