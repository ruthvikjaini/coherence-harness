import pytest

from coherence.state import StaleVersionError, VersionedStore


def test_set_and_get_versions_increment():
    store = VersionedStore()
    fact = store.set("k", 1, writer="a")
    assert fact.version == 1
    assert store.set("k", 2, writer="b").version == 2
    assert store.value("k") == 2
    assert store.version("k") == 2


def test_missing_key_defaults():
    store = VersionedStore()
    assert store.get("missing") is None
    assert store.value("missing") is None
    assert store.value("missing", default=7) == 7
    assert store.version("missing") == 0


def test_compare_and_swap_accepts_current_and_rejects_stale():
    store = VersionedStore()
    store.set("k", "v1", writer="a")
    store.set("k", "v2", writer="b", expected_version=1)
    with pytest.raises(StaleVersionError):
        store.set("k", "v3", writer="c", expected_version=1)
    assert store.value("k") == "v2"


def test_delete_requires_current_version_and_records_history():
    store = VersionedStore()
    store.set("k", 1, writer="a")
    with pytest.raises(StaleVersionError):
        store.delete("k", writer="b", expected_version=99)
    assert store.delete("k", writer="b", expected_version=1) is True
    assert store.get("k") is None
    with pytest.raises(KeyError):
        store.delete("k", writer="b")


def test_history_keeps_only_state_altering_events_in_order():
    store = VersionedStore()
    store.set("a", 1, writer="w1")
    store.set("b", 2, writer="w1")
    store.set("a", 3, writer="w2")
    kinds = [(e.kind, e.key, e.version) for e in store.history]
    assert kinds == [("SET", "a", 1), ("SET", "b", 1), ("SET", "a", 2)]
    assert [e.seq for e in store.history] == [1, 2, 3]


def test_recorded_revert_restores_old_value_and_is_audited():
    store = VersionedStore()
    store.set("k", "v1", writer="a")
    store.set("k", "v2", writer="a")
    store.revert_to("k", 1, writer="admin")
    assert store.value("k") == "v1"
    assert store.history[-1].kind == "SET"
    assert store.history[-1].writer == "admin"
    with pytest.raises(KeyError):
        store.revert_to("k", 99, writer="admin")


def test_verify_current_catches_silent_external_change():
    store = VersionedStore()
    store.set("cfg", "v3", writer="harness")
    assert store.verify_current("cfg", "v3") is True
    store.force_external_set("cfg", "v2")
    assert store.verify_current("cfg", "v3") is False
    assert store.verify_current("cfg", "v2") is True
    assert store.verify_current("absent", "v2") is False


def test_snapshot_is_point_in_time():
    store = VersionedStore()
    store.set("k", 1, writer="a")
    snap = store.snapshot()
    store.set("k", 2, writer="b")
    assert snap["k"] == (1, 1)
    assert store.snapshot()["k"] == (2, 2)


def test_keys_sorted():
    store = VersionedStore()
    store.set("z", 1, writer="a")
    store.set("a", 1, writer="a")
    assert store.keys() == ["a", "z"]
