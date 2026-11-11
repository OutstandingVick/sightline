"""Grants.

User-issued, time-boxed, revocable spending permissions. Created, listed and revoked
ONLY through the human ``/sightline`` slash command; no model-callable tool writes here.

A grant covers one token on one network, a set of recipients (or "*" when the user
explicitly said "to any"), a per-transaction maximum and a cap per rolling 24h, 7 days or 30 days. What has
been spent is computed from the audit log at check time, never stored as a counter.
Expiry and revocation are also evaluated at check time.
"""

from __future__ import annotations

import json
import secrets
import time
from dataclasses import asdict, dataclass, field
from decimal import Decimal

from . import audit
from .db import connect


DAY = 24 * 3600
PERIODS = {"day": DAY, "week": 7 * DAY, "month": 30 * DAY}


def period_label(period_s: int) -> str:
    return {DAY: "24h", 7 * DAY: "7d", 30 * DAY: "30d"}.get(period_s, f"{period_s // 3600}h")


@dataclass
class Grant:
    id: str
    created_at: float
    expires_at: float
    network: str
    token: str  # "SOL" or mint address
    symbol: str
    max_per_tx: str  # Decimal as string
    daily_cap: str
    recipients: list[str] = field(default_factory=list)  # ["*"] = any recipient
    note: str = ""
    revoked_at: float | None = None
    period_s: int = DAY  # the cap ("daily_cap" for history) applies per rolling period: 24h, 7d or 30d

    @property
    def period_label(self) -> str:
        return period_label(self.period_s)

    def status(self, now: float | None = None) -> str:
        now = time.time() if now is None else now
        if self.revoked_at is not None:
            return "revoked"
        if now >= self.expires_at:
            return "expired"
        return "active"

    def allows_recipient(self, recipient: str) -> bool:
        return self.recipients == ["*"] or recipient in self.recipients

    def to_dict(self) -> dict:
        return asdict(self)


def _token_key(intent) -> str:
    return "SOL" if intent.kind == "transfer_sol" else intent.mint


def _save(conn, g: Grant) -> None:
    conn.execute("INSERT OR REPLACE INTO grants (id, created_at, data) VALUES (?, ?, ?)",
                 (g.id, g.created_at, json.dumps(g.to_dict())))


def create(*, network: str, token: str, symbol: str, daily_cap: Decimal, max_per_tx: Decimal | None,
           recipients: list[str], duration_s: int, note: str = "", now: float | None = None,
           period_s: int = DAY) -> Grant:
    if daily_cap <= 0:
        raise ValueError("daily cap must be positive")
    per_tx = daily_cap if max_per_tx is None else max_per_tx
    if per_tx <= 0 or per_tx > daily_cap:
        raise ValueError("max per tx must be positive and at most the daily cap")
    if not recipients:
        raise ValueError("name recipients with `to <addr>` (or `to any`)")
    if duration_s <= 0:
        raise ValueError("duration must be positive")
    if period_s not in PERIODS.values():
        raise ValueError("cap period must be per day, week or month")
    now = time.time() if now is None else now
    from .db import transaction

    with transaction() as conn:
        gid = "g_" + secrets.token_hex(2)
        while conn.execute("SELECT 1 FROM grants WHERE id = ?", (gid,)).fetchone():
            gid = "g_" + secrets.token_hex(3)
        g = Grant(id=gid, created_at=now, expires_at=now + duration_s, network=network, token=token,
                  symbol=symbol, max_per_tx=str(per_tx), daily_cap=str(daily_cap),
                  recipients=list(recipients), note=note, period_s=period_s)
        _save(conn, g)
        audit.append("grant_created", g.to_dict(), conn=conn, ts=now)
    return g


def list_grants(conn=None) -> list[Grant]:
    own = conn is None
    conn = conn or connect()
    try:
        rows = conn.execute("SELECT data FROM grants ORDER BY created_at DESC").fetchall()
    finally:
        if own:
            conn.close()
    return [Grant(**json.loads(r[0])) for r in rows]


def get(grant_id: str, conn=None) -> Grant | None:
    return next((g for g in list_grants(conn) if g.id == grant_id), None)


def revoke(grant_id: str, now: float | None = None) -> Grant | None:
    from .db import transaction

    now = time.time() if now is None else now
    with transaction() as conn:
        g = get(grant_id, conn)
        if g is None or g.revoked_at is not None:
            return g
        g.revoked_at = now
        _save(conn, g)
        audit.append("grant_revoked", {"id": g.id}, conn=conn, ts=now)
    return g


def revoke_all(now: float | None = None) -> list[str]:
    now = time.time() if now is None else now
    return [g.id for g in list_grants() if g.status(now) == "active" and revoke(g.id, now)]


def remaining(g: Grant, conn=None, now: float | None = None) -> Decimal:
    return Decimal(g.daily_cap) - audit.spent_in_window(g.id, g.period_s, conn=conn, now=now)


def find_matching(intent, network: str, conn=None, now: float | None = None) -> tuple[Grant | None, str]:
    """Return (grant, "") for the first grant that covers the intent, else (None, why not).

    Call inside ``db.transaction`` when the answer is used to reserve spend.
    """
    now = time.time() if now is None else now
    amount = Decimal(intent.amount)
    token = _token_key(intent)
    reasons: list[str] = []
    candidates = [g for g in list_grants(conn) if g.network == network and g.token == token]
    if not candidates:
        return None, f"no grant for {intent.symbol or token} on {network}"
    for g in candidates:
        status = g.status(now)
        if status != "active":
            reasons.append(f"grant {g.id} {status}")
            continue
        if not g.allows_recipient(intent.recipient):
            reasons.append(f"recipient not in grant {g.id}")
            continue
        if amount > Decimal(g.max_per_tx):
            reasons.append(f"exceeds per-tx max of grant {g.id}: {amount} > {g.max_per_tx}")
            continue
        spent = audit.spent_in_window(g.id, g.period_s, conn=conn, now=now)
        if spent + amount > Decimal(g.daily_cap):
            reasons.append(f"exceeds the {g.period_label} cap of grant {g.id}: {spent}/{g.daily_cap} used")
            continue
        return g, ""
    return None, "; ".join(reasons)
