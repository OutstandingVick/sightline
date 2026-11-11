"""Per-recipient budgets: a grant's cap can apply per rolling day, week or month."""

from decimal import Decimal

import pytest

import sightline.commands  # noqa: F401  (import before fixtures, like the other test modules)
import sightline.grants  # noqa: F401
from sightline import audit, commands, grants
from sightline.intents import Intent

ALICE = "7xKqGNm1r5h6tqk3Vb3vKXg6wZ8bq4o5bS2mF8yQ9fP2"
T0 = 1_800_000_000.0
DAY = 24 * 3600


def pay(amount):
    return Intent("transfer_sol", ALICE, amount, decimals=9, symbol="SOL")


def spend(g, amount, ts):
    audit.append("execute", {"grant_id": g.id, "amount": amount, "intent": {}}, ts=ts)


def weekly(cap="5", per_tx="2"):
    return grants.create(network="devnet", token="SOL", symbol="SOL", daily_cap=Decimal(cap),
                         max_per_tx=Decimal(per_tx), recipients=[ALICE], duration_s=30 * DAY,
                         now=T0, period_s=7 * DAY)


def test_weekly_cap_counts_the_whole_week():
    g = weekly()
    spend(g, "2", T0 + 1 * DAY)
    spend(g, "2", T0 + 3 * DAY)
    found, why = grants.find_matching(pay("2"), "devnet", now=T0 + 5 * DAY)
    assert found is None and why == f"exceeds the 7d cap of grant {g.id}: 4/5 used"
    assert grants.find_matching(pay("1"), "devnet", now=T0 + 5 * DAY)[0] == g


def test_weekly_cap_rolls():
    g = weekly()
    spend(g, "2", T0 + 1 * DAY)
    spend(g, "2", T0 + 3 * DAY)
    assert grants.find_matching(pay("2"), "devnet", now=T0 + 8.5 * DAY)[0] == g  # day-1 spend aged out
    assert grants.remaining(g, now=T0 + 8.5 * DAY) == Decimal(3)


def test_default_period_is_still_24h():
    g = grants.create(network="devnet", token="SOL", symbol="SOL", daily_cap=Decimal(5), max_per_tx=None,
                      recipients=[ALICE], duration_s=DAY, now=T0)
    assert g.period_s == DAY and g.period_label == "24h"


def test_old_grants_without_period_load_as_daily():
    import json

    from sightline.db import connect

    conn = connect()
    data = {"id": "g_0ld0", "created_at": T0, "expires_at": T0 + DAY, "network": "devnet", "token": "SOL",
            "symbol": "SOL", "max_per_tx": "1", "daily_cap": "1", "recipients": ["*"], "note": "", "revoked_at": None}
    conn.execute("INSERT INTO grants (id, created_at, data) VALUES (?, ?, ?)", ("g_0ld0", T0, json.dumps(data)))
    conn.close()
    assert grants.get("g_0ld0").period_s == DAY


def test_bad_period_rejected():
    with pytest.raises(ValueError, match="per day, week or month"):
        grants.create(network="devnet", token="SOL", symbol="SOL", daily_cap=Decimal(1), max_per_tx=None,
                      recipients=[ALICE], duration_s=DAY, period_s=12 * 3600)


@pytest.mark.parametrize("words,period,duration", [
    ("per week", 7 * DAY, 7 * DAY),            # a weekly budget lasts at least a week by default
    ("per month", 30 * DAY, 30 * DAY),
    ("per 7d for 60d", 7 * DAY, 60 * DAY),
    ("per day", DAY, DAY),
    ("", DAY, DAY),
])
def test_slash_command_parses_period(words, period, duration):
    p = commands.parse_grant(f"5 SOL {words} to {ALICE}".split())
    assert p["period_s"] == period and p["duration_s"] == duration


def test_slash_command_text_shows_period():
    out = commands.handle(f"grant 5 SOL per week to {ALICE} max 2")
    assert "per rolling 7d" in out
    assert "5/5 SOL left (7d)" in commands.handle("grants")
    assert "5 SOL/7d" in commands.handle("log 1")
    assert "bad period" in commands.handle(f"grant 5 SOL per fortnight to {ALICE}")


@pytest.mark.attack
def test_weekly_budget_cannot_be_drained_by_splitting():
    """Many small payments in one week still stop at the weekly cap."""
    g = weekly(cap="1", per_tx="0.3")
    for i in range(3):
        spend(g, "0.3", T0 + i * DAY)
    assert grants.find_matching(pay("0.1"), "devnet", now=T0 + 3 * DAY)[0] == g
    spend(g, "0.1", T0 + 3 * DAY)
    found, why = grants.find_matching(pay("0.1"), "devnet", now=T0 + 4 * DAY)
    assert found is None and "7d cap" in why


def test_usage_error_explains_budgets():
    out = commands.handle("grant 5")
    assert "grant needs <cap> <token>" in out and "per week" in out
