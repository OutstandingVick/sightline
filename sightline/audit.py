"""Audit log.

Append-only, hash-chained record of every permission change and every signing
decision. Rows are never updated: a send is an ``execute`` event followed by a
``sent`` or ``failed`` event that references it. Each row's hash covers the
previous row's hash, so editing or deleting history breaks ``verify()``.

Events:
    grant_created, grant_revoked      — permission changes (human, via slash command)
    decision                          — firewall verdict for a pay attempt (ALLOW / APPROVE / BLOCK)
    execute                           — spend reserved: about to sign (grant id or "human")
    sent / failed                     — outcome of an execute (``ref`` = its seq)
"""

from __future__ import annotations

import hashlib
import json
import time
from decimal import Decimal

from .db import connect

GENESIS = "0" * 64
DAY = 24 * 3600


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _hash(prev: str, seq: int, ts: float, event: str, data: dict) -> str:
    return hashlib.sha256(f"{prev}|{seq}|{ts!r}|{event}|{_canonical(data)}".encode()).hexdigest()


def append(event: str, data: dict, conn=None, ts: float | None = None) -> int:
    """Append one event. Call inside ``db.transaction`` when it must be atomic with a check."""
    own = conn is None
    conn = conn or connect()
    try:
        row = conn.execute("SELECT seq, hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        seq, prev = (row[0] + 1, row[1]) if row else (1, GENESIS)
        ts = time.time() if ts is None else ts
        conn.execute(
            "INSERT INTO audit (seq, ts, event, data, prev_hash, hash) VALUES (?, ?, ?, ?, ?, ?)",
            (seq, ts, event, _canonical(data), prev, _hash(prev, seq, ts, event, data)),
        )
        return seq
    finally:
        if own:
            conn.close()


def entries(limit: int | None = None, conn=None) -> list[dict]:
    own = conn is None
    conn = conn or connect()
    try:
        sql = "SELECT seq, ts, event, data, prev_hash, hash FROM audit ORDER BY seq DESC"
        rows = conn.execute(sql + (" LIMIT ?" if limit else ""), (limit,) if limit else ()).fetchall()
    finally:
        if own:
            conn.close()
    return [{"seq": r[0], "ts": r[1], "event": r[2], "data": json.loads(r[3]),
             "prev_hash": r[4], "hash": r[5]} for r in reversed(rows)]


def verify(conn=None) -> tuple[bool, str]:
    """Recompute the hash chain. Returns (ok, message)."""
    prev = GENESIS
    rows = entries(conn=conn)
    for e in rows:
        if e["prev_hash"] != prev or _hash(prev, e["seq"], e["ts"], e["event"], e["data"]) != e["hash"]:
            return False, f"chain broken at entry #{e['seq']}"
        prev = e["hash"]
    return True, f"{len(rows)} entries, chain intact (head {prev[:12]})"


def spent_24h(grant_id: str, conn=None, now: float | None = None) -> Decimal:
    """Sum of reserved spends against a grant in the last 24h, minus those that failed.

    Derived from the log (not a counter), so it can't drift from what actually happened.
    """
    now = time.time() if now is None else now
    own = conn is None
    conn = conn or connect()
    try:
        rows = conn.execute(
            "SELECT seq, data FROM audit WHERE event = 'execute' AND ts > ?", (now - DAY,)).fetchall()
        failed = {json.loads(d)["ref"] for (d,) in conn.execute(
            "SELECT data FROM audit WHERE event = 'failed' AND ts > ?", (now - DAY - 600,)).fetchall()}
    finally:
        if own:
            conn.close()
    total = Decimal(0)
    for seq, data in rows:
        d = json.loads(data)
        if d.get("grant_id") == grant_id and seq not in failed:
            total += Decimal(d["amount"])
    return total
