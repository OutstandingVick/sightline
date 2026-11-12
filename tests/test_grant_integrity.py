"""Grant rows are only trusted when they match the hash-chained audit log (an editor of data.db can't widen them)."""

import json
from decimal import Decimal

import pytest

import sightline.grants  # noqa: F401  (import before fixtures, like the other test modules)
from sightline import audit, grants
from sightline.db import connect
from sightline.intents import Intent

A = "7xKqGNm1r5h6tqk3Vb3vKXg6wZ8bq4o5bS2mF8yQ9fP2"
B = "535pnQVzoGKSkvTpwEm8WaAHZeRRkUvwi2HCw8M9CyBg"
pytestmark = pytest.mark.attack


def pay(to=A, amount="1"):
    return Intent("transfer_sol", to, amount, decimals=9, symbol="SOL")


def make():
    return grants.create(network="devnet", token="SOL", symbol="SOL", daily_cap=Decimal(2), max_per_tx=Decimal(1),
                         recipients=[A], duration_s=3600)


def edit_row(gid, **changes):
    conn = connect()
    data = json.loads(conn.execute("SELECT data FROM grants WHERE id = ?", (gid,)).fetchone()[0])
    data.update(changes)
    conn.execute("UPDATE grants SET data = ? WHERE id = ?", (json.dumps(data), gid))
    conn.close()


def test_untouched_grant_still_works():
    g = make()
    assert grants.find_matching(pay(), "devnet")[0] == g


@pytest.mark.parametrize("changes", [
    {"daily_cap": "1000", "max_per_tx": "1000"},  # widen the cap
    {"recipients": ["*"]},                         # open it to anyone
    {"expires_at": 9_999_999_999},                 # extend it
])
def test_edited_row_is_refused(changes):
    g = make()
    edit_row(g.id, **changes)
    found, why = grants.find_matching(pay(to=B) if "recipients" in changes else pay(), "devnet")
    assert found is None and "doesn't match its audit record" in why


def test_un_revoking_in_the_table_does_not_work():
    g = make()
    grants.revoke(g.id)
    edit_row(g.id, revoked_at=None)
    found, why = grants.find_matching(pay(), "devnet")
    assert found is None and f"grant {g.id} revoked" in why


def test_inserted_row_without_audit_record_is_refused():
    conn = connect()
    data = {"id": "g_beef", "created_at": 1.0, "expires_at": 9_999_999_999, "network": "devnet", "token": "SOL",
            "symbol": "SOL", "max_per_tx": "100", "daily_cap": "100", "recipients": ["*"], "note": "",
            "revoked_at": None, "period_s": 86400}
    conn.execute("INSERT INTO grants (id, created_at, data) VALUES (?, ?, ?)", ("g_beef", 1.0, json.dumps(data)))
    conn.close()
    found, why = grants.find_matching(pay(), "devnet")
    assert found is None and "g_beef has no creation record" in why


def test_forged_audit_row_breaks_the_chain_and_disables_all_grants():
    make()
    conn = connect()
    seq = conn.execute("SELECT MAX(seq) FROM audit").fetchone()[0] + 1
    forged = {"id": "g_f00d", "created_at": 1.0, "expires_at": 9_999_999_999, "network": "devnet", "token": "SOL",
              "symbol": "SOL", "max_per_tx": "100", "daily_cap": "100", "recipients": ["*"], "note": "",
              "revoked_at": None, "period_s": 86400}
    conn.execute("INSERT INTO audit (seq, ts, event, data, prev_hash, hash) VALUES (?, ?, ?, ?, ?, ?)",
                 (seq, 2.0, "grant_created", json.dumps(forged), "0" * 64, "f" * 64))
    conn.execute("INSERT INTO grants (id, created_at, data) VALUES (?, ?, ?)", ("g_f00d", 1.0, json.dumps(forged)))
    conn.close()
    found, why = grants.find_matching(pay(to=B), "devnet")
    assert found is None and "audit log failed verification" in why
    assert grants.find_matching(pay(), "devnet")[0] is None  # even the honest grant stops working
    assert not audit.verify()[0]
