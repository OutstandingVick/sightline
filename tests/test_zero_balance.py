"""An empty wallet must not hide the firewall: policy verdict first, funding problem second.

Fail-closed is unchanged — nothing here is ever sent — only the reported reason ordering.
"""

import importlib
import json
from decimal import Decimal

import pytest
from fakes import FakeClient
from solders.keypair import Keypair

import sightline.commands  # noqa: F401  (import before fixtures, like the other test modules)
import sightline.firewall  # noqa: F401
import sightline.state  # noqa: F401

DEST = str(Keypair().pubkey())
OTHER = str(Keypair().pubkey())
attack = pytest.mark.attack


@pytest.fixture
def env(plugin, ctx, keypair, monkeypatch, cluster):
    plugin.register(ctx)
    pkg = plugin.__name__ + ".sightline"
    client = FakeClient(lamports=0)
    cluster.payer_lamports = 0
    monkeypatch.setattr(importlib.import_module(pkg + ".wallet"), "Client", lambda *a, **k: client)
    grants = importlib.import_module(pkg + ".grants")
    importlib.import_module(pkg + ".gate")._cache.clear()
    hook = ctx.hooks["pre_tool_call"][0]

    def call(args):
        """Hermes: hook first; a block stops; otherwise the handler runs (with its second gate)."""
        d = hook(tool_name="sightline_pay", args=args, session_id="s", task_id="t")
        out = json.loads(ctx.tools["sightline_pay"]["handler"](args, session_id="s"))
        return d, out

    def grant(to=(DEST,), cap="0.05", per_tx="0.02", duration_s=3600):
        return grants.create(network="devnet", token="SOL", symbol="SOL", daily_cap=Decimal(cap),
                             max_per_tx=Decimal(per_tx), recipients=list(to), duration_s=duration_s)

    def preview(args):
        return json.loads(ctx.tools["sightline_preview"]["handler"](args))

    env = type("Env", (), {})()
    env.call, env.grant, env.preview, env.client, env.grants = call, grant, preview, client, grants
    return env


def blocked(d, out):
    assert d["action"] == "block"
    assert out["sent"] is False if "sent" in out else True
    return d["message"]


def test_preview_says_wallet_is_empty(env):
    out = env.preview({"recipient": DEST, "amount": 0.01})
    assert out["error"] == "empty_wallet" and "hermes sightline setup" in out["next_step"]


@attack
def test_no_grant_reports_policy_then_funding(env):
    d, out = env.call({"recipient": DEST, "amount": 0.01})
    msg = blocked(d, out)
    assert msg.startswith("Sightline BLOCK: no grant covers this")
    assert "(Also: wallet has 0 SOL — run `hermes sightline setup` for funding options.)" in msg
    assert out["message"].startswith("Sightline BLOCK: no grant covers this") and env.client.sent == []


@attack
def test_recipient_not_in_grant_reported_first(env):
    env.grant(to=(DEST,))
    d, out = env.call({"recipient": OTHER, "amount": 0.01})
    msg = blocked(d, out)
    assert "no grant covers this: recipient not in grant" in msg and "wallet has 0 SOL" in msg


@attack
def test_over_per_tx_cap_reported_first(env):
    env.grant(per_tx="0.02")
    msg = blocked(*env.call({"recipient": DEST, "amount": 0.03}))
    assert "exceeds per-tx max" in msg and "wallet has 0 SOL" in msg


@attack
def test_revoked_grant_reported_first(env):
    g = env.grant()
    env.grants.revoke(g.id)
    msg = blocked(*env.call({"recipient": DEST, "amount": 0.01}))
    assert f"grant {g.id} revoked" in msg and "wallet has 0 SOL" in msg


@attack
def test_expired_grant_reported_first(env, monkeypatch):
    g = env.grant(duration_s=1)
    import time

    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + 10)
    msg = blocked(*env.call({"recipient": DEST, "amount": 0.01}))
    assert f"grant {g.id} expired" in msg


@attack
def test_matching_grant_still_blocks_when_unfunded(env):
    g = env.grant()
    d, out = env.call({"recipient": DEST, "amount": 0.01})
    msg = blocked(d, out)
    assert msg.startswith(f"Sightline BLOCK: covered by grant {g.id}, but wallet has 0 SOL")
    assert out["error"] == "empty_wallet" and env.client.sent == []  # fail closed


@attack
def test_drain_reported_as_drain_at_zero_balance(env):
    env.grant(to=("*",), cap="100", per_tx="100")  # even a generous grant can't authorise a drain
    d, out = env.call({"recipient": OTHER, "amount": "all"})
    msg = blocked(d, out)
    assert msg.startswith("Sightline BLOCK: asks to send the entire SOL balance")
    assert out["error"] == "blocked" and out["decision"]["rule"] == "drain" and env.client.sent == []


@attack
def test_drain_by_amount_when_funded(plugin, ctx, keypair, monkeypatch, cluster):
    """With SOL in the wallet, an amount that would leave < 0.01 SOL is a policy BLOCK before simulation."""
    plugin.register(ctx)
    pkg = plugin.__name__ + ".sightline"
    client = FakeClient(lamports=1_000_000_000)
    cluster.payer_lamports = 1_000_000_000
    monkeypatch.setattr(importlib.import_module(pkg + ".wallet"), "Client", lambda *a, **k: client)
    hook = ctx.hooks["pre_tool_call"][0]
    d = hook(tool_name="sightline_pay", args={"recipient": DEST, "amount": 1}, session_id="s", task_id="t")
    assert d["action"] == "block" and "0.01 SOL reserve (wallet holds 1 SOL)" in d["message"]


@attack
def test_mainnet_without_opt_in_reported_first(env, monkeypatch):
    monkeypatch.setenv("SIGHTLINE_RPC_URL", "https://api.mainnet-beta.solana.com")
    d, out = env.call({"recipient": DEST, "amount": 0.01})
    assert d["action"] == "block" and out["error"] == "mainnet_refused"


@attack
def test_failed_simulation_never_allows():
    """Unit level: a grant plus a failed simulation is BLOCK, never ALLOW."""
    from sightline.firewall import BLOCK, decide
    from sightline.intents import Intent
    from sightline.simulate import SimulationReport

    class S:
        network, allow_mainnet = "devnet", False

    report = SimulationReport(ok=False, error="boom", error_code="simulation_failed", sol_pre_lamports=10**9)
    d = decide(Intent("transfer_sol", DEST, "0.01", decimals=9, symbol="SOL"), report, S())
    assert d.verdict == BLOCK and "simulation failed: boom" in d.reason


def test_pane_and_log_show_the_policy_reason(env):
    from sightline import commands, state

    env.call({"recipient": DEST, "amount": 0.01})
    feed = state.get_state()["recent_audit"]
    assert feed[0]["verdict"] == "BLOCK" and feed[0]["reason"].startswith("no grant covers this")
    assert "no grant covers this" in commands.handle("log 2")


def test_paying_yourself_is_named_as_such(plugin, ctx, keypair, monkeypatch, cluster):
    plugin.register(ctx)
    pkg = plugin.__name__ + ".sightline"
    monkeypatch.setattr(importlib.import_module(pkg + ".wallet"), "Client", lambda *a, **k: FakeClient())
    hook = ctx.hooks["pre_tool_call"][0]
    d = hook(tool_name="sightline_pay", args={"recipient": str(keypair.pubkey()), "amount": 0.01},
             session_id="s", task_id="t")
    assert d["action"] == "block" and "this wallet's own address" in d["message"]
    assert "That address is this wallet" in d["message"] or "address is this wallet" in d["message"]
