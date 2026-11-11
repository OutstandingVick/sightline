"""Solana Pay links go through the same hook, grants, simulation and firewall as typed payments."""

import importlib
import json
from decimal import Decimal

import pytest
from fakes import FakeClient
from solders.keypair import Keypair

DEST = str(Keypair().pubkey())
OTHER = str(Keypair().pubkey())
REF = str(Keypair().pubkey())
attack = pytest.mark.attack


@pytest.fixture
def env(plugin, ctx, keypair, monkeypatch):
    plugin.register(ctx)
    pkg = plugin.__name__ + ".sightline"
    client = FakeClient()
    monkeypatch.setattr(importlib.import_module(pkg + ".wallet"), "Client", lambda *a, **k: client)
    grants = importlib.import_module(pkg + ".grants")
    importlib.import_module(pkg + ".gate")._cache.clear()
    hook = ctx.hooks["pre_tool_call"][0]
    pay = ctx.tools["sightline_pay"]["handler"]

    def call(args, approve=False):
        d = hook(tool_name="sightline_pay", args=args, session_id="s", task_id="t")
        if d and (d["action"] == "block" or (d["action"] == "approve" and not approve)):
            return d, None
        return d, json.loads(pay(args, session_id="s"))

    def grant(to=(DEST,), cap="1", per_tx="0.5"):
        return grants.create(network="devnet", token="SOL", symbol="SOL", daily_cap=Decimal(cap),
                             max_per_tx=Decimal(per_tx), recipients=list(to), duration_s=3600)

    e = type("Env", (), {})()
    e.call, e.grant, e.client, e.hook, e.pay = call, grant, client, hook, pay
    e.preview = lambda args: json.loads(ctx.tools["sightline_preview"]["handler"](args))
    return e


def link(to=DEST, amount="0.1", **extra):
    q = "&".join(f"{k.replace('_', '-')}={v}" for k, v in {"amount": amount, **extra}.items())
    return f"solana:{to}?{q}"


def test_preview_a_link(env):
    out = env.preview({"link": link(label="Coffee%20Shop", memo="order-42")})
    assert out["would_succeed"] and out["summary"].startswith("You send 0.1 SOL to Coffee Shop (")
    assert 'Memo: "order-42".' in out["summary"]
    assert "Memo" in [k.split(".")[0] for k in out["simulation"]["instructions"]]


def test_link_inside_grant_is_allowed_and_sent_with_memo_and_reference(env):
    g = env.grant()
    d, out = env.call({"link": link(memo="order-42", reference=REF)})
    assert d is None and out["sent"] and out["approved_by"] == f"grant {g.id}"
    tx = env.client.sent[0]
    msg = tx.message
    keys = [str(k) for k in msg.account_keys]
    assert REF in keys and bytes(msg.instructions[0].data) == b"order-42"
    assert out["intent"]["references"] == [REF] and out["intent"]["memo"] == "order-42"


@attack
def test_link_cannot_bypass_grant_recipients(env):
    env.grant(to=(DEST,))
    d, out = env.call({"link": link(to=OTHER)})
    assert d["action"] == "approve" and out is None and env.client.sent == []


@attack
def test_link_cannot_exceed_per_tx_max(env):
    env.grant(per_tx="0.05")
    d, _ = env.call({"link": link(amount="0.1")})
    assert d["action"] == "approve" and "exceeds per-tx max" in d["message"] and env.client.sent == []


@attack
def test_transaction_request_link_is_blocked(env):
    env.grant(to=("*",))
    d, _ = env.call({"link": "solana:https://merchant.example/api/pay"})
    assert d["action"] == "block" and "transaction request" in d["message"] and env.client.sent == []


@attack
def test_link_conflicting_with_args_is_blocked(env):
    env.grant(to=("*",))
    d, _ = env.call({"link": link(to=DEST), "recipient": OTHER})
    assert d["action"] == "block" and "doesn't match the payment link" in d["message"]
    d, _ = env.call({"link": link(amount="0.1"), "amount": 0.2})
    assert d["action"] == "block" and env.client.sent == []


@attack
def test_approval_is_bound_to_the_exact_link(env):
    """A human approves link A; the handler must not use that approval for link B."""
    d = env.hook(tool_name="sightline_pay", args={"link": link(amount="0.1")}, session_id="s", task_id="t")
    assert d["action"] == "approve"
    out = json.loads(env.pay({"link": link(amount="0.2")}, session_id="s"))
    assert out["error"] == "blocked" and "approval" in out["message"] and env.client.sent == []


def test_link_drain_is_still_a_drain(env):
    env.grant(to=("*",), cap="100", per_tx="100")
    d, _ = env.call({"link": link(amount="9.995")})  # the fake cluster holds 10 SOL
    assert d["action"] == "block" and "0.01 SOL reserve" in d["message"]


@attack
def test_unattended_contract(env):
    """What makes cron/bot payments safe: inside a grant the hook needs nobody (returns None);
    outside it the hook demands a human (approve), which Hermes refuses when nobody is there."""
    env.grant(to=(DEST,))
    inside = env.hook(tool_name="sightline_pay", args={"link": link(to=DEST)}, session_id="cron", task_id="t")
    outside = env.hook(tool_name="sightline_pay", args={"link": link(to=OTHER)}, session_id="cron", task_id="t")
    assert inside is None
    assert outside["action"] == "approve" and outside["rule_key"].startswith("sightline:")
