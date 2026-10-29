"""A versioned shared-state store with an append-only history.

Every mutation that goes through the store is recorded in ``history``,
which keeps only state-altering events (the minimal history D in Heng
2026). A write that names an ``expected_version`` older than the current
version is rejected, so an agent working from a stale snapshot cannot
silently overwrite newer state. ``force_external_set`` exists only to
simulate an out-of-band change (a silent revert by something outside the
harness); it deliberately bypasses history, which is exactly what the
harness's current-state check at commit time is designed to catch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class StaleVersionError(ValueError):
    """Raised when a write names a version that is no longer current."""


@dataclass
class Fact:
    key: str
    value: Any
    version: int
    writer: str
    provenance: str = ""


@dataclass
class HistoryEntry:
    seq: int
    kind: str  # SET, DELETE, REVERT
    key: str
    value: Any
    version: int
    writer: str


@dataclass
class VersionedStore:
    _facts: dict = field(default_factory=dict)
    _history: list = field(default_factory=list)

    def get(self, key: str):
        """Return the Fact for ``key``, or None if it is absent."""
        return self._facts.get(key)

    def value(self, key: str, default=None):
        fact = self._facts.get(key)
        return default if fact is None else fact.value

    def version(self, key: str) -> int:
        fact = self._facts.get(key)
        return 0 if fact is None else fact.version

    def set(self, key, value, writer, expected_version=None, provenance=""):
        """Write ``value``. With ``expected_version`` set, the write is a
        compare-and-swap: it fails unless the current version matches."""
        current = self._facts.get(key)
        current_version = 0 if current is None else current.version
        if expected_version is not None and expected_version != current_version:
            raise StaleVersionError(
                f"{key}: expected version {expected_version}, "
                f"current version is {current_version}"
            )
        new_version = current_version + 1
        fact = Fact(key=key, value=value, version=new_version,
                    writer=writer, provenance=provenance)
        self._facts[key] = fact
        self._history.append(HistoryEntry(
            seq=len(self._history) + 1, kind="SET", key=key, value=value,
            version=new_version, writer=writer))
        return fact

    def delete(self, key, writer, expected_version=None):
        current = self._facts.get(key)
        if current is None:
            raise KeyError(key)
        if expected_version is not None and expected_version != current.version:
            raise StaleVersionError(
                f"{key}: expected version {expected_version}, "
                f"current version is {current.version}"
            )
        del self._facts[key]
        self._history.append(HistoryEntry(
            seq=len(self._history) + 1, kind="DELETE", key=key, value=None,
            version=current.version + 1, writer=writer))
        return True

    def revert_to(self, key, target_version, writer):
        """Recorded revert to a previously seen value. Unlike a silent
        revert, this is an explicit history entry, so the audit trail
        still explains the state."""
        for entry in reversed(self._history):
            if entry.key == key and entry.version == target_version and entry.kind == "SET":
                return self.set(key, entry.value, writer, provenance="revert")
        raise KeyError(f"no recorded version {target_version} for {key!r}")

    def force_external_set(self, key, value):
        """Simulation-only out-of-band change that bypasses history.

        This models a silent revert by an external system. Production
        code must never call it; the harness detects its effect by
        re-reading current state at commit time.
        """
        current = self._facts.get(key)
        version = 1 if current is None else current.version + 1
        self._facts[key] = Fact(key=key, value=value, version=version,
                                writer="<external>", provenance="external")

    def snapshot(self):
        """A point-in-time copy of keys, values and versions."""
        return {k: (f.value, f.version) for k, f in self._facts.items()}

    def verify_current(self, key, expected_value) -> bool:
        """True only if the store's current value equals ``expected_value``.

        A checker holding a stale snapshot fails this after a silent
        external change; the harness re-reads, so it passes.
        """
        fact = self._facts.get(key)
        return fact is not None and fact.value == expected_value

    @property
    def history(self):
        return list(self._history)

    def keys(self):
        return sorted(self._facts)
