"""Read model for the Desktop pane: one JSON-safe snapshot of wallet, grants and audit.

Public data only: network, public key, balances, grants and audit entries. The
keypair never leaves ``Settings`` and nothing here serialises it. Each part fails
on its own (an RPC outage still shows grants and the log).
"""

from __future__ import annotations

import time
from decimal import Decimal

from . import audit, grants
from .config import DEFAULT_RPC_URL, network_from_url, read_env

RECENT_AUDIT = 50
SHOW_ENDED_FOR_S = 24 * 3600


def _error(exc: Exception) -> dict:
    return {"code": getattr(exc, "code", type(exc).__name__),
            "message": getattr(exc, "message", None) or "unavailable"}


def _wallet_part() -> dict:
    from .config import load_settings
    from .wallet import Wallet

    try:
        settings = load_settings()
    except Exception as exc:
        network = network_from_url(read_env("SIGHTLINE_RPC_URL") or DEFAULT_RPC_URL)
        return {"network": network, "pubkey": None, "balances": None, "wallet_error": _error(exc)}, None
    out = {"network": settings.network, "pubkey": str(settings.public_key), "balances": None,
           "wallet_error": None}
    try:
        out["balances"] = Wallet(settings).get_balances()
    except Exception as exc:
        out["wallet_error"] = _error(exc)
    return out, settings


def grant_view(g, now: float) -> dict:
    status = g.status(now)
    remaining = grants.remaining(g, now=now) if status == "active" else None
    used = (Decimal(g.daily_cap) - remaining) if remaining is not None else None
    return {
        "id": g.id, "status": status, "network": g.network, "token": g.token, "symbol": g.symbol,
        "daily_cap": g.daily_cap, "max_per_tx": g.max_per_tx,
        "used_24h": None if used is None else str(used.normalize()),
        "remaining_24h": None if remaining is None else str(remaining.normalize()),
        "recipients": list(g.recipients), "note": g.note,
        "created_at": g.created_at, "expires_at": g.expires_at, "revoked_at": g.revoked_at,
    }


def audit_view(e: dict, settings) -> dict:
    d = e["data"]
    view = {"seq": e["seq"], "ts": e["ts"], "event": e["event"]}
    if e["event"] == "decision":
        intent = d.get("intent") or {}
        view.update(verdict=d.get("verdict"), reason=d.get("reason"), rule=d.get("rule"),
                    grant_id=d.get("grant_id"), source=d.get("source"),
                    explanation=d.get("explanation") or "",
                    amount=intent.get("amount"), symbol=intent.get("symbol"),
                    recipient=intent.get("recipient"))
    elif e["event"] == "execute":
        intent = d.get("intent") or {}
        view.update(amount=intent.get("amount"), symbol=intent.get("symbol"),
                    recipient=intent.get("recipient"), grant_id=d.get("grant_id"),
                    approval=d.get("approval"))
    elif e["event"] == "sent":
        sig = d.get("signature")
        view.update(ref=d.get("ref"), signature=sig,
                    explorer_url=settings.explorer_url(sig) if settings and sig else None)
    elif e["event"] == "failed":
        view.update(ref=d.get("ref"), error=d.get("error"), message=d.get("message"))
    elif e["event"] in ("grant_created", "grant_revoked"):
        view.update(grant_id=d.get("id"), symbol=d.get("symbol"), daily_cap=d.get("daily_cap"))
    return view


def get_state(limit: int = RECENT_AUDIT, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    wallet, settings = _wallet_part()
    shown = [g for g in grants.list_grants()
             if g.status(now) == "active" or now - (g.revoked_at or g.expires_at) < SHOW_ENDED_FOR_S]
    rows = audit.entries(limit=limit)
    ok, chain = audit.verify()
    return {
        **wallet,
        "grants": [grant_view(g, now) for g in shown],
        "recent_audit": [audit_view(e, settings) for e in reversed(rows)],  # newest first
        "audit_ok": ok, "audit_status": chain,
        "now": now,
    }


def revoke(grant_id: str) -> dict:
    """Revoke one grant (narrows permissions only). Writes a grant_revoked audit row."""
    g = grants.get(grant_id)
    if g is None:
        return {"ok": False, "error": "not_found", "message": f"No grant {grant_id}."}
    if g.status() != "active":
        return {"ok": False, "error": "not_active", "message": f"{grant_id} is already {g.status()}."}
    g = grants.revoke(grant_id)
    return {"ok": True, "grant": grant_view(g, time.time())}
