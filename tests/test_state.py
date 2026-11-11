"""The Desktop pane's read model: shape, revoke, and the audit row it writes."""

from decimal import Decimal

import pytest
from fakes import FakeClient

import sightline.state  # noqa: F401  (import before fixtures run, like the other test modules)
import sightline.wallet  # noqa: F401


@pytest.fixture
def client(monkeypatch, keypair):
    import sightline.wallet as wallet_mod

    c = FakeClient(lamports=1_500_000_000)
    monkeypatch.setattr(wallet_mod, "Client", lambda *a, **k: c)
    return c


def test_state_shape(client, keypair, grant_any):
    from sightline.state import get_state

    s = get_state()
    assert set(s) >= {"network", "pubkey", "balances", "grants", "recent_audit", "audit_ok"}
    assert s["network"] == "devnet"
    assert s["pubkey"] == str(keypair.pubkey())
    assert s["balances"]["sol"] == "1.5"
    assert s["wallet_error"] is None
    (g,) = s["grants"]
    assert g["id"] == grant_any.id and g["status"] == "active"
    assert g["used_24h"] == "0" and g["remaining_24h"] == "100"
    assert g["recipients"] == ["*"] and g["expires_at"] > s["now"]
    assert s["recent_audit"][0]["event"] == "grant_created"
    assert s["audit_ok"] is True


def test_audit_newest_first_and_limited(client, keypair):
    from sightline import audit
    from sightline.state import get_state

    for i in range(60):
        audit.append("decision", {"verdict": "BLOCK", "reason": f"r{i}", "intent": {}})
    feed = get_state()["recent_audit"]
    assert len(feed) == 50
    assert feed[0]["reason"] == "r59" and feed[-1]["reason"] == "r10"


def test_decision_and_sent_views(client, keypair):
    from sightline import audit
    from sightline.state import get_state

    intent = {"recipient": "76nKQ7uBMB482NqeVxUjyNXbq2kq741TmbKM9umLTRX1", "amount": "0.01", "symbol": "SOL"}
    audit.append("decision", {"verdict": "ALLOW", "reason": "covered by grant g_abcd", "rule": "grant g_abcd",
                              "grant_id": "g_abcd", "source": "hook", "intent": intent,
                              "explanation": "Send 0.01 SOL to 76nK…TRX1"})
    seq = audit.append("execute", {"intent": intent, "grant_id": "g_abcd", "approval": "grant"})
    audit.append("sent", {"ref": seq, "signature": "5ig"})
    sent, execute, decision = get_state()["recent_audit"][:3]
    assert decision["verdict"] == "ALLOW" and decision["explanation"].startswith("Send 0.01 SOL")
    assert decision["amount"] == "0.01" and decision["rule"] == "grant g_abcd"
    assert execute["approval"] == "grant"
    assert sent["explorer_url"] == "https://explorer.solana.com/tx/5ig?cluster=devnet"


def test_rpc_outage_still_shows_grants(monkeypatch, keypair, grant_any):
    import sightline.wallet as wallet_mod
    from sightline.state import get_state

    class Down(FakeClient):
        def get_balance(self, *a, **k):
            raise ConnectionError("rpc down")

    monkeypatch.setattr(wallet_mod, "Client", lambda *a, **k: Down())
    s = get_state()
    assert s["balances"] is None and s["wallet_error"]
    assert s["pubkey"] == str(keypair.pubkey())
    assert [g["id"] for g in s["grants"]] == [grant_any.id]


def test_missing_key_still_shows_network(monkeypatch):
    from sightline.state import get_state

    monkeypatch.delenv("SIGHTLINE_SECRET_KEY", raising=False)
    s = get_state()
    assert s["pubkey"] is None and s["wallet_error"]["code"]
    assert s["network"] == "devnet"


def test_used_reflects_spend(client, keypair, grant_any):
    from sightline import audit
    from sightline.state import get_state

    audit.append("execute", {"intent": {"amount": "2.5"}, "grant_id": grant_any.id, "amount": "2.5",
                             "approval": "grant"})
    (g,) = get_state()["grants"]
    assert Decimal(g["used_24h"]) == Decimal("2.5") and Decimal(g["remaining_24h"]) == Decimal("97.5")


def test_revoke_revokes_and_audits(client, keypair, grant_any):
    from sightline import audit
    from sightline.state import get_state, revoke

    out = revoke(grant_any.id)
    assert out["ok"] and out["grant"]["status"] == "revoked"
    assert audit.entries()[-1]["event"] == "grant_revoked"
    assert audit.entries()[-1]["data"]["id"] == grant_any.id
    assert get_state()["grants"][0]["status"] == "revoked"
    assert audit.verify()[0]


def test_revoke_unknown_or_twice(client, keypair, grant_any):
    from sightline.state import revoke

    assert revoke("g_ffff")["error"] == "not_found"
    revoke(grant_any.id)
    assert revoke(grant_any.id)["error"] == "not_active"


def test_ended_grants_hidden_after_a_day(client, keypair, grant_any):
    import time

    from sightline.state import get_state

    later = time.time() + 3600 + 25 * 3600
    assert get_state(now=later)["grants"] == []
    assert get_state(now=time.time() + 3601)["grants"][0]["status"] == "expired"


def test_failed_and_grant_event_views(client, keypair):
    from sightline import audit
    from sightline.state import get_state

    seq = audit.append("execute", {"intent": {"amount": "1"}, "grant_id": None, "approval": "human"})
    audit.append("failed", {"ref": seq, "error": "send_failed", "message": "blockhash expired"})
    failed = get_state()["recent_audit"][0]
    assert failed["event"] == "failed" and failed["ref"] == seq and failed["error"] == "send_failed"


def test_revoke_expired_grant_is_refused(client, keypair, monkeypatch):
    from decimal import Decimal

    from sightline import grants
    from sightline.state import revoke

    g = grants.create(network="devnet", token="SOL", symbol="SOL", daily_cap=Decimal(1), max_per_tx=None,
                      recipients=["*"], duration_s=1, now=1.0)
    assert revoke(g.id)["error"] == "not_active"


def test_no_wallet_tells_the_pane_what_to_do(monkeypatch):
    from sightline.state import get_state

    monkeypatch.delenv("SIGHTLINE_SECRET_KEY", raising=False)
    err = get_state()["wallet_error"]
    assert err["code"] == "missing_secret" and "/sightline setup" in err["next_step"]


def test_grant_view_reports_period(client, keypair):
    from decimal import Decimal

    from sightline import grants
    from sightline.state import get_state

    grants.create(network="devnet", token="SOL", symbol="SOL", daily_cap=Decimal(5), max_per_tx=None,
                  recipients=["*"], duration_s=7 * 86400, period_s=7 * 86400)
    s = get_state()
    assert s["grants"][0]["period"] == "7d" and s["grants"][0]["period_s"] == 7 * 86400
    assert s["recent_audit"][0]["period"] == "7d"
