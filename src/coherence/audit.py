"""Audit helpers: export the harness audit trail as JSON lines."""

from __future__ import annotations

import json


def audit_to_jsonl(audit_entries) -> str:
    return "\n".join(json.dumps(entry, sort_keys=True) for entry in audit_entries)


def audit_summary(audit_entries) -> dict:
    total = len(audit_entries)
    accepted = sum(1 for e in audit_entries if e["accepted"])
    violations = {}
    for entry in audit_entries:
        for code in entry["violations"]:
            violations[code] = violations.get(code, 0) + 1
    return {"entries": total, "accepted": accepted,
            "rejected": total - accepted, "violations": violations}
