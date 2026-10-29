"""Command-line interface.

Subcommands:
  audit     check one JSON proposal file against a fresh harness
  scenario  run one named scenario and print JSON
  compare   run the effort-escalation comparison and print JSON
  demo      print a short worked walkthrough
"""

from __future__ import annotations

import argparse
import json
import sys

from .budgets import Budget, Ledger
from .escalation import run_comparison
from .harness import CommitMode, Harness, Intent, Proposal
from .scenarios import revision_benchmark, silent_revert, team_bench, unit_overlap
from .state import VersionedStore
from .units import Quantity


def _proposal_from_dict(data: dict) -> Proposal:
    intents = []
    for raw in data.get("intents", []):
        amount = None
        if raw.get("amount") is not None:
            amount = Quantity(float(raw["amount"]), raw["unit"])
        intents.append(Intent(
            kind=raw["kind"], key=raw.get("key", ""),
            value=raw.get("value"), amount=amount, unit=raw.get("unit"),
            budget=raw.get("budget", ""),
            expected_version=raw.get("expected_version"),
            reservation_id=raw.get("reservation_id"),
            owner=data.get("worker_id", "")))
    return Proposal(worker_id=data.get("worker_id", "cli"),
                    intents=intents, scope=data.get("scope", ""))


def _fresh_harness() -> Harness:
    harness = Harness(store=VersionedStore(), ledger=Ledger())
    harness.ledger.add_budget(Budget("calls", Quantity(100, "calls")))
    harness.ledger.add_budget(Budget("budget", Quantity(1000, "USD")))
    return harness


def cmd_audit(args) -> int:
    with open(args.file) as handle:
        data = json.load(handle)
    harness = _fresh_harness()
    for alias, canonical in data.get("aliases", {}).items():
        harness.add_alias(alias, canonical)
    mode = CommitMode(args.mode)
    result = harness.commit(_proposal_from_dict(data), mode=mode)
    print(json.dumps({
        "accepted": result.accepted,
        "mode": mode.value,
        "violations": [{"code": v.code, "message": v.message,
                        "invariant": v.invariant} for v in result.violations],
        "applied": result.applied,
    }, indent=2))
    return 0


def cmd_scenario(args) -> int:
    if args.name == "team-bench":
        result = team_bench(args.seed, mode=CommitMode(args.mode))
    elif args.name == "revision":
        result = revision_benchmark(args.seed, visible=args.visible)
    elif args.name == "silent-revert":
        result = silent_revert(args.seed)
    elif args.name == "unit-overlap":
        result = unit_overlap(args.seed)
    else:
        raise ValueError(f"unknown scenario: {args.name!r}")
    print(json.dumps(result, indent=2))
    return 0


def cmd_compare(args) -> int:
    print(json.dumps(run_comparison(args.tasks, args.seed), indent=2))
    return 0


def cmd_demo(_args) -> int:
    harness = _fresh_harness()
    print("Coherence harness demo: two workers, one shared budget of 100 calls.")
    for worker in ("worker-0", "worker-1"):
        proposal = Proposal(worker, [Intent(
            kind="spend", key="work", amount=Quantity(60, "calls"),
            unit="calls", budget="calls", owner=worker)])
        result = harness.commit(proposal)
        print(f"{worker}: accepted={result.accepted} "
              f"violations={[v.code for v in result.violations]}")
    spent = harness.ledger.total_spent("calls")
    print(f"Total spent: {spent.value} {spent.unit} (cap 100) — second spend rejected.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="coherence")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("audit")
    p.add_argument("file")
    p.add_argument("--mode", choices=["blind", "visible", "enforce"], default="enforce")
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("scenario")
    p.add_argument("name", choices=["team-bench", "revision", "silent-revert", "unit-overlap"])
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--mode", choices=["blind", "visible", "enforce"], default="enforce")
    p.add_argument("--visible", action="store_true")
    p.set_defaults(func=cmd_scenario)

    p = sub.add_parser("compare")
    p.add_argument("--tasks", type=int, default=200)
    p.add_argument("--seed", type=int, default=0)
    p.set_defaults(func=cmd_compare)

    sub.add_parser("demo").set_defaults(func=cmd_demo)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
