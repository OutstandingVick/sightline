"""Live updates for the Desktop pane.

After a transaction that wrote audit rows commits (a firewall decision, a send, a
grant created or revoked), Sightline emits ``plugin.sightline.audit`` on Hermes'
global event stream so the pane re-reads its state instead of polling.

Uses Hermes' public ``broadcast_plugin_event``. Outside a process with a Desktop
client attached (CLI, cron, tests) it is a no-op. Never raises: a missing UI must
not change what the firewall does.
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

PLUGIN_ID = "sightline"
AUDIT_EVENT = "audit"

_pending = threading.local()


def mark_dirty() -> None:
    """Called by audit.append: an event is owed once the current transaction commits."""
    _pending.dirty = True


def discard() -> None:
    """Called on rollback: nothing was written, so nothing to announce."""
    _pending.dirty = False


def flush() -> None:
    """Called after commit: emit one event if anything was written."""
    if not getattr(_pending, "dirty", False):
        return
    _pending.dirty = False
    emit(AUDIT_EVENT)


def emit(event: str, payload: dict | None = None) -> bool:
    try:
        from hermes_cli.plugin_events import broadcast_plugin_event
    except ImportError:
        return False
    try:
        broadcast_plugin_event(PLUGIN_ID, event, payload or {})
        return True
    except Exception:  # the UI is best-effort; never let it affect a payment path
        logger.debug("sightline: event emit failed", exc_info=True)
        return False
