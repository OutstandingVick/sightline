"""Live pane events: one event after a committed write, none after a rollback."""

import sys
import types

import pytest

import sightline.audit  # noqa: F401
import sightline.events
from sightline import audit, events
from sightline.db import transaction


@pytest.fixture
def emitted(monkeypatch):
    calls = []
    mod = types.ModuleType("hermes_cli.plugin_events")
    mod.broadcast_plugin_event = lambda pid, ev, payload=None: calls.append((pid, ev, payload))
    monkeypatch.setitem(sys.modules, "hermes_cli", types.ModuleType("hermes_cli"))
    monkeypatch.setitem(sys.modules, "hermes_cli.plugin_events", mod)
    events.discard()
    return calls


def test_append_emits_once_after_commit(emitted):
    audit.append("decision", {"verdict": "BLOCK"})
    assert emitted == [("sightline", "audit", {})]


def test_one_event_per_transaction(emitted):
    with transaction() as conn:
        audit.append("execute", {}, conn=conn)
        audit.append("sent", {}, conn=conn)
        assert emitted == []  # nothing until commit
    assert len(emitted) == 1


def test_rollback_emits_nothing(emitted):
    with pytest.raises(RuntimeError):
        with transaction() as conn:
            audit.append("execute", {}, conn=conn)
            raise RuntimeError("boom")
    assert emitted == []
    audit.append("decision", {})
    assert len(emitted) == 1  # the rolled-back row did not leave a stale flag behind


def test_grant_changes_emit(emitted, grant_any):
    from sightline import grants

    assert len(emitted) == 1  # grant_created
    grants.revoke(grant_any.id)
    assert len(emitted) == 2


def test_no_hermes_is_a_noop(monkeypatch):
    monkeypatch.setitem(sys.modules, "hermes_cli.plugin_events", None)
    assert events.emit("audit") is False
    audit.append("decision", {})  # must not raise


def test_broken_broadcast_never_raises(monkeypatch, emitted):
    def boom(*a, **k):
        raise RuntimeError("no transport")

    sys.modules["hermes_cli.plugin_events"].broadcast_plugin_event = boom
    audit.append("decision", {})  # payment path unaffected
    assert audit.verify()[0]
