"""Short demo: run the team-budget scenario in each commit mode."""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from coherence.harness import CommitMode  # noqa: E402
from coherence.scenarios import team_bench  # noqa: E402


def main() -> int:
    for mode in (CommitMode.BLIND, CommitMode.VISIBLE, CommitMode.ENFORCE):
        result = team_bench(seed=0, mode=mode)
        print(f"{mode.value}: spent={result['total_spent']} "
              f"accepted={result['accepted']} rejected={result['rejected']} "
              f"over_cap={result['over_cap']}")
    print(json.dumps(team_bench(seed=0, mode=CommitMode.ENFORCE), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
