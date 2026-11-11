"""The human-only ``/sightline`` slash command: the ONLY way to create or revoke grants.

Slash commands are typed by the user; the model has no tool that reaches this code.

  /sightline grant <cap> <token> [per day|week|month] to <addr>[,<addr>]|any [for 1h|24h|7d|30d] [max <per_tx>] [note "..."]
  /sightline grants
  /sightline revoke <id> | /sightline revoke all
  /sightline log [n]
  /sightline verify
  /sightline setup [--no-airdrop]
"""

from __future__ import annotations

import re
import shlex
import time
from datetime import datetime
from decimal import Decimal

from . import audit, grants
from .amounts import AmountError, format_amount, to_decimal
from .config import DEFAULT_RPC_URL, network_from_url, read_env
from .tokens import KNOWN_MINTS, AddressError, parse_address, short

USAGE = """Usage:
  /sightline grant <cap> <token> [per day|week|month] to <addr>[,<addr>]|any [for 1h|24h|7d|30d] [max <per_tx>] [note "..."]
     e.g. /sightline grant 5 USDC to <address> for 1h max 2
  /sightline grants              list grants and what is left of each
  /sightline revoke <id>|all     revoke one or every grant
  /sightline log [n]             last n audit entries (default 10)
  /sightline verify              check the audit log's hash chain
  /sightline setup               create + fund a devnet wallet (keeps an existing one)"""

_DURATION = re.compile(r"^(\d+)([mhd])$")
_UNIT = {"m": 60, "h": 3600, "d": 86400}


class UsageError(ValueError):
    pass


def parse_duration(text: str) -> int:
    m = _DURATION.match(text.strip().lower())
    if not m or int(m.group(1)) == 0:
        raise UsageError(f"bad duration {text!r}; use e.g. 30m, 1h, 24h, 7d")
    return int(m.group(1)) * _UNIT[m.group(2)]


def _network() -> str:
    return network_from_url(read_env("SIGHTLINE_RPC_URL") or DEFAULT_RPC_URL)


def _resolve_token(raw: str, network: str) -> tuple[str, str]:
    """(token key, display symbol): "SOL", a known symbol's mint, or a mint address."""
    if raw.upper() == "SOL":
        return "SOL", "SOL"
    mint = KNOWN_MINTS.get(network, {}).get(raw.upper())
    if mint:
        return mint, raw.upper()
    try:
        return str(parse_address(raw, "token mint")), short(raw)
    except AddressError:
        raise UsageError(f"unknown token {raw!r}; use SOL, a known symbol or a mint address") from None


def parse_grant(argv: list[str]) -> dict:
    if len(argv) < 2:
        raise UsageError("grant needs <cap> <token>, e.g. 5 USDC (add 'per week' or 'per month' for a longer budget)")
    try:
        cap = to_decimal(argv[0])
    except AmountError as exc:
        raise UsageError(f"bad daily amount: {exc}") from None
    network = _network()
    token, symbol = _resolve_token(argv[1], network)
    out = {"network": network, "token": token, "symbol": symbol, "daily_cap": cap, "max_per_tx": None,
           "recipients": [], "duration_s": 24 * 3600, "note": "", "period_s": grants.DAY}
    rest = argv[2:]
    i = 0
    period_set = duration_set = False
    while i < len(rest):
        word = rest[i].lower()
        if i + 1 >= len(rest):
            raise UsageError(f"'{rest[i]}' needs a value")
        value = rest[i + 1]
        if word == "to":
            if value.lower() == "any":
                out["recipients"] = ["*"]
            else:
                try:
                    out["recipients"] = [str(parse_address(a, "recipient")) for a in value.split(",") if a]
                except AddressError as exc:
                    raise UsageError(str(exc)) from None
        elif word == "for":
            out["duration_s"] = parse_duration(value)
            duration_set = True
        elif word == "max":
            try:
                out["max_per_tx"] = to_decimal(value)
            except AmountError as exc:
                raise UsageError(f"bad max: {exc}") from None
        elif word == "per":
            period = grants.PERIODS.get(value.lower()) or {"24h": grants.DAY, "7d": 7 * grants.DAY,
                                                          "30d": 30 * grants.DAY}.get(value.lower())
            if period is None:
                raise UsageError(f"bad period {value!r}; use per day, per week or per month")
            out["period_s"] = period
            period_set = True
        elif word == "note":
            out["note"] = value[:200]
        else:
            raise UsageError(f"unexpected '{rest[i]}'")
        i += 2
    if period_set and not duration_set:  # a weekly budget that expires after a day would be pointless
        out["duration_s"] = max(out["duration_s"], out["period_s"])
    if not out["recipients"]:
        raise UsageError("say who may be paid: `to <addr>[,<addr>]` (or `to any` to allow every recipient)")
    return out


def _n(value) -> str:
    """Amounts the same way everywhere: plain decimal, no trailing zeros ("0.05", never "0.050" or "5E-2")."""
    return format_amount(Decimal(str(value)))


def _when(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def _left(seconds: float) -> str:
    seconds = int(max(0, seconds))
    if seconds >= 86400:
        return f"{seconds // 86400}d{(seconds % 86400) // 3600}h"
    if seconds >= 3600:
        return f"{seconds // 3600}h{(seconds % 3600) // 60}m"
    return f"{seconds // 60}m"


def _recipients(g) -> str:
    return "any" if g.recipients == ["*"] else ", ".join(short(r) for r in g.recipients)


def describe(g, now: float | None = None) -> str:
    now = time.time() if now is None else now
    status = g.status(now)
    left = (f"{_n(grants.remaining(g, now=now))}/{_n(g.daily_cap)} {g.symbol} left ({g.period_label})"
            if status == "active" else status)
    expiry = f"expires in {_left(g.expires_at - now)}" if status == "active" else f"ended {_when(g.revoked_at or g.expires_at)}"
    note = f' — "{g.note}"' if g.note else ""
    return (f"{g.id}  {g.symbol} on {g.network.upper()}: max {_n(g.max_per_tx)}/tx, {left}; "
            f"to {_recipients(g)}; {expiry}{note}")


def cmd_grant(argv: list[str]) -> str:
    p = parse_grant(argv)
    try:
        g = grants.create(**p)
    except ValueError as exc:
        raise UsageError(str(exc)) from None
    who = "ANY recipient" if g.recipients == ["*"] else _recipients(g)
    return (f"Granted {g.id}: the agent may send up to {_n(g.daily_cap)} {g.symbol} per rolling {g.period_label} "
            f"(max {_n(g.max_per_tx)} per tx) to {who} on {g.network.upper()}, until {_when(g.expires_at)}."
            + (f' Note: "{g.note}".' if g.note else "")
            + f"\nRevoke any time: /sightline revoke {g.id}")


def cmd_grants() -> str:
    now = time.time()
    rows = [g for g in grants.list_grants()
            if g.status(now) == "active" or now - (g.revoked_at or g.expires_at) < 7 * 86400]
    if not rows:
        return "No grants. Every payment needs your approval.\n" + USAGE.splitlines()[1]
    return "\n".join(describe(g, now) for g in rows)


def cmd_revoke(argv: list[str], ask=None) -> str:
    if not argv and ask is not None:
        active = [g for g in grants.list_grants() if g.status() == "active"]
        if active:
            choice = ask("Revoke which grant?", [{"value": g.id, "label": g.id, "description": describe(g)}
                                                  for g in active] + [{"value": "all", "label": "all"}])
            argv = [choice] if choice else []
    if not argv:
        raise UsageError("revoke needs a grant id or 'all'")
    if argv[0].lower() == "all":
        ids = grants.revoke_all()
        return f"Revoked {len(ids)} grant(s): {', '.join(ids)}" if ids else "No active grants to revoke."
    g = grants.revoke(argv[0])
    if g is None:
        return f"No grant {argv[0]}."
    return f"Revoked {g.id}. It no longer authorises any payment."


def _summarise(e: dict) -> str:
    d = e["data"]
    ev = e["event"]
    if ev == "decision":
        i = d.get("intent") or {}
        return (f"{d.get('verdict')} ({d.get('source')}) {i.get('amount')} {i.get('symbol') or ''} → "
                f"{short(i.get('recipient', '?'))}: {d.get('reason')}")
    if ev == "execute":
        i = d.get("intent") or {}
        return f"signing {i.get('amount')} {i.get('symbol') or ''} → {short(i.get('recipient', '?'))} via {d.get('approval')} {d.get('grant_id') or ''}".rstrip()
    if ev == "sent":
        return f"sent #{d.get('ref')}: {d.get('signature')}"
    if ev == "failed":
        return f"failed #{d.get('ref')}: {d.get('error')} {d.get('message') or ''}".rstrip()
    if ev == "grant_created":
        return (f"grant {d.get('id')} created: {d.get('daily_cap')} {d.get('symbol')}/"
                f"{grants.period_label(d.get('period_s') or grants.DAY)}")
    if ev == "grant_revoked":
        return f"grant {d.get('id')} revoked"
    return ev


def cmd_log(argv: list[str]) -> str:
    try:
        n = max(1, min(200, int(argv[0]))) if argv else 10
    except ValueError:
        raise UsageError("log takes a number") from None
    rows = audit.entries(limit=n)
    if not rows:
        return "Audit log is empty."
    unanswered = _unanswered_approvals(audit.entries(limit=n + 500))
    lines = []
    for e in rows:
        line = f"#{e['seq']} {_when(e['ts'])} {_summarise(e)}"
        if e["seq"] in unanswered:
            line += "  → not approved; treated as BLOCK, nothing sent"
        lines.append(line)
    return "\n".join(lines)


APPROVAL_WINDOW_S = 15 * 60


def _unanswered_approvals(rows: list[dict], now: float | None = None) -> set[int]:
    """Hook APPROVE decisions with no human-approved execute of the same intent afterwards.

    Hermes runs the tool only after a human says yes (and fails closed when nobody can
    answer), so an approval request that was never followed by an execute was refused.
    Requests younger than the approval window are still pending and are left alone.
    """
    now = time.time() if now is None else now
    out = set()
    for i, e in enumerate(rows):
        d = e["data"]
        if e["event"] != "decision" or d.get("verdict") != "APPROVE" or d.get("source") != "hook":
            continue
        if now - e["ts"] < APPROVAL_WINDOW_S:
            continue
        answered = any(
            later["event"] == "execute" and later["data"].get("approval") == "human"
            and later["data"].get("intent") == d.get("intent")
            and later["ts"] - e["ts"] <= APPROVAL_WINDOW_S
            for later in rows[i + 1:]
        )
        if not answered:
            out.add(e["seq"])
    return out


def cmd_setup(argv: list[str]) -> str:
    from . import setup

    try:
        return "\n".join(setup.run(airdrop="--no-airdrop" not in argv))
    except ModuleNotFoundError as exc:
        return f"Python package {exc.name!r} is missing. Run `hermes plugins enable sightline`, then restart Hermes."


def cmd_verify() -> str:
    ok, msg = audit.verify()
    return ("✓ " if ok else "✗ ") + msg


def handle(raw_args: str, ask=None) -> str:
    try:
        argv = shlex.split(raw_args or "")
    except ValueError as exc:
        return f"Could not parse: {exc}\n{USAGE}"
    if not argv or argv[0] in ("help", "-h", "--help"):
        return USAGE
    sub, rest = argv[0].lower(), argv[1:]
    try:
        if sub == "grant":
            return cmd_grant(rest)
        if sub == "grants":
            return cmd_grants()
        if sub == "revoke":
            return cmd_revoke(rest, ask)
        if sub == "log":
            return cmd_log(rest)
        if sub == "verify":
            return cmd_verify()
        if sub == "setup":
            return cmd_setup(rest)
    except UsageError as exc:
        return f"{exc}\n\n{USAGE}"
    return f"Unknown subcommand {argv[0]!r}.\n\n{USAGE}"
