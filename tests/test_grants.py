from decimal import Decimal

import pytest

from sightline import audit, grants
from sightline.intents import Intent

A = "7xKqGNm1r5h6tqk3Vb3vKXg6wZ8bq4o5bS2mF8yQ9fP2"
B = "535pnQVzoGKSkvTpwEm8WaAHZeRRkUvwi2HCw8M9CyBg"
T0 = 1_800_000_000.0


def sol(amount, to=A):
    return Intent("transfer_sol", to, str(amount), None, 9, "SOL")


def make(cap="5", per_tx=None, to=(A,), dur=3600, token="SOL", now=T0):
    return grants.create(network="devnet", token=token, symbol="SOL" if token == "SOL" else "X",
                         daily_cap=Decimal(cap), max_per_tx=None if per_tx is None else Decimal(per_tx),
                         recipients=list(to), duration_s=dur, now=now)


def spend(g, amount, ts, failed=False):
    seq = audit.append("execute", {"grant_id": g.id, "amount": str(amount)}, ts=ts)
    if failed:
        audit.append("failed", {"ref": seq}, ts=ts)


def test_defaults_and_validation():
    g = make(cap="5")
    assert g.max_per_tx == "5" and g.id.startswith("g_") and g.status(T0) == "active"
    with pytest.raises(ValueError):
        make(cap="5", per_tx="6")
    with pytest.raises(ValueError):
        make(to=())


def test_match_and_reasons():
    assert grants.find_matching(sol(1), "devnet", now=T0) == (None, "no grant for SOL on devnet")
    g = make(cap="5", per_tx="2")
    assert grants.find_matching(sol(2), "devnet", now=T0)[0].id == g.id
    assert "per-tx max" in grants.find_matching(sol(3), "devnet", now=T0)[1]
    assert "recipient not in grant" in grants.find_matching(sol(1, to=B), "devnet", now=T0)[1]
    assert grants.find_matching(sol(1), "mainnet", now=T0)[0] is None


def test_expiry_evaluated_at_check_time():
    g = make(dur=60)
    assert grants.find_matching(sol(1), "devnet", now=T0 + 59)[0].id == g.id
    assert grants.find_matching(sol(1), "devnet", now=T0 + 61)[1] == f"grant {g.id} expired"


def test_revoke():
    g = make()
    grants.revoke(g.id, now=T0 + 1)
    assert grants.find_matching(sol(1), "devnet", now=T0 + 2)[1] == f"grant {g.id} revoked"
    assert [e["event"] for e in audit.entries()] == ["grant_created", "grant_revoked"]


def test_revoke_all():
    a, b = make(), make(to=(B,))
    assert sorted(grants.revoke_all(now=T0 + 1)) == sorted([a.id, b.id])


def test_daily_cap_rolls_and_ignores_failed():
    g = make(cap="5")
    spend(g, 3, T0 + 10)
    spend(g, 2, T0 + 20, failed=True)
    assert audit.spent_24h(g.id, now=T0 + 30) == 3
    _, why = grants.find_matching(sol("2.5"), "devnet", now=T0 + 30)
    assert why == f"exceeds daily cap of grant {g.id}: 3/5 used"
    assert grants.find_matching(sol(2), "devnet", now=T0 + 30)[0].id == g.id
    # 24h after the 3 SOL spend it no longer counts (grant still active: make a long one)
    long = make(cap="5", dur=3 * 86400, to=(B,))
    spend(long, 5, T0 + 100)
    assert grants.find_matching(sol(1, to=B), "devnet", now=T0 + 101)[0] is None
    assert grants.find_matching(sol(1, to=B), "devnet", now=T0 + 100 + 86401)[0].id == long.id


def test_any_recipient_only_when_explicit():
    make(to=("*",))
    assert grants.find_matching(sol(1, to=B), "devnet", now=T0)[0] is not None
