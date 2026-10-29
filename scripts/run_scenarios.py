"""Run all scenarios and the escalation comparison, write results files.

Usage: python scripts/run_scenarios.py [--seed-file ...]
Writes results/experiment.json (full output) and results/measured.json
(the small set of numbers quoted in the README).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from coherence.escalation import run_comparison  # noqa: E402
from coherence.scenarios import run_all  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="results/experiment.json")
    args = parser.parse_args()
    started = time.time()
    scenarios = run_all(seeds=(0, 1, 2, 3, 4))
    comparison_seed0 = run_comparison(n_tasks=200, seed=0)
    comparison_seed42 = run_comparison(n_tasks=200, seed=42)
    experiment = {
        "scenarios": scenarios,
        "escalation": {"seed_0": comparison_seed0, "seed_42": comparison_seed42},
        "runtime_seconds": round(time.time() - started, 3),
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(experiment, indent=2, sort_keys=True) + "\n")

    team = scenarios["team_bench"]
    revision = scenarios["revision"]
    measured = {
        "team_bench_runs_per_mode": team["enforce"]["runs"],
        "team_bench_violating_runs": {
            mode: team[mode]["violating_runs"] for mode in ("blind", "visible", "enforce")
        },
        "team_bench_mean_total_spent": {
            mode: team[mode]["mean_total_spent"] for mode in ("blind", "visible", "enforce")
        },
        "revision_hidden_mean_accuracy": revision["hidden"]["mean_accuracy"],
        "revision_visible_mean_accuracy": revision["visible"]["mean_accuracy"],
        "revision_n_per_run": 40,
        "revision_runs_per_setting": revision["hidden"]["runs"],
        "silent_revert_mean_stale_checker_score": scenarios["silent_revert"]["mean_stale_checker_score"],
        "silent_revert_mean_harness_score": scenarios["silent_revert"]["mean_harness_score"],
        "unit_overlap_agreeing_disagreements": scenarios["unit_overlap"]["agreeing_disagreements"],
        "unit_overlap_disagreeing_disagreements": scenarios["unit_overlap"]["disagreeing_disagreements"],
        "escalation_seed_0": comparison_seed0,
        "escalation_seed_42": comparison_seed42,
        "runtime_seconds": experiment["runtime_seconds"],
    }
    measured_path = out.parent / "measured.json"
    measured_path.write_text(json.dumps(measured, indent=2, sort_keys=True) + "\n")
    print(f"wrote {out} and {measured_path} in {experiment['runtime_seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
