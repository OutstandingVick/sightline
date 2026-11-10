"""End-to-end enforcement: hook → (human) → handler, with the second gate in execute_intent."""

import importlib
import json
import threading
from decimal import Decimal

import pytest
from fakes import FakeClient
from solders.keypair import Keypair

DEST = str(Keypair().pubkey())
OTHER = str(Keypair().pubkey())


@pytest.fixture
def env(plugin, ctx, keypair, monkeypatch):
    plugin.register(ctx)
    pkg = plugin.__name__ + ".sightline"
    client = FakeClient()
    monkeypatch.setattr(importlib.import_module(pkg + ".wallet"), "Client", lambda *a, **k: client)
    grants = importlib.import_module(pkg + ".grants")
    audit = importlib.import_module(pkg + ".audit")
    gate = importlib.import_module(pkg + ".gate")
    gate._cache.clear()
    hook = ctx.hooks["pre_tool_call"][0]
    pay = ctx.tools["sightline_pay"]["handler"]

    def call(args, session="s1", approve=None):
        """Mimic Hermes: run the hook; block/deny stops; otherwise dispatch the handler."""
        d = hook(tool_name="sightline_pay", args=args, session_id=session, task_id="t")
        if d and d["action"] == "block":
            return d, None
        if d and d["action"] == "approve" and not approve:
            return d, None
        return d, json.loads(pay(args, session_id=session))

    def grant(cap="1", to=(DEST,), per_tx=None):
        return grants.create(network="devnet", token="SOL", symbol="SOL", daily_cap=Decimal(cap),
                             max_per_tx=None if per_tx is None else Decimal(per_tx),
                             recipients=list(to), duration_s=3600)

    return NS(call=call, grant=grant, client=client, audit=audit, grants=grants, hook=hook, pay=pay, gate=gate)


class NS:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_hook_ignores_other_tools(env):
    assert env.hook(tool_name="terminal", args={"command": "ls"}, session_id="s") is None
    assert env.hook(tool_name="sightline_balance", args={}, session_id="s") is None


def test_grant_allows_and_sends(env):
    g = env.grant()
    d, out = env.call({"recipient": DEST, "amount": 0.5})
    assert d is None and out["sent"] and out["approved_by"] == f"grant {g.id}"
    assert len(env.client.sent) == 1
    assert [e["event"] for e in env.audit.entries()][-3:] == ["decision", "execute", "sent"]


def test_no_grant_asks_human_with_unique_rule_key(env):
    d1, out = env.call({"recipient": DEST, "amount": 0.5})
    d2, _ = env.call({"recipient": DEST, "amount": 0.5})
    assert d1["action"] == "approve" and out is None and env.client.sent == []
    assert "No grant covers this: no grant for SOL on devnet. Approve this one payment?" in d1["message"]
    assert "You send 0.5 SOL" in d1["message"]
    assert d1["rule_key"] != d2["rule_key"] and d1["rule_key"].startswith("sightline:")


def test_human_approval_sends_once(env):
    d, out = env.call({"recipient": DEST, "amount": 0.5}, approve=True)
    assert d["action"] == "approve" and out["sent"] and out["approved_by"] == "human"
    # the approval was single-use: a direct second dispatch without the hook is refused
    again = json.loads(env.pay({"recipient": DEST, "amount": 0.5}, session_id="s1"))
    assert again["error"] == "blocked" and "none was given" in again["message"]
    assert len(env.client.sent) == 1


def test_handler_without_hook_never_sends_unapproved(env):
    out = json.loads(env.pay({"recipient": DEST, "amount": 0.5}, session_id="s1"))
    assert out["error"] == "blocked" and out["sent"] is False and env.client.sent == []


def test_approval_bound_to_session_and_args(env):
    env.call({"recipient": DEST, "amount": 0.5}, session="s1")  # hook asks, human hasn't answered
    other_session = json.loads(env.pay({"recipient": DEST, "amount": 0.5}, session_id="s2"))
    other_amount = json.loads(env.pay({"recipient": DEST, "amount": 0.6}, session_id="s1"))
    assert other_session["error"] == other_amount["error"] == "blocked" and env.client.sent == []


def test_hard_block_from_hook(env):
    env.grant(cap="100", to=("*",))
    d, out = env.call({"recipient": DEST, "amount": 1000})  # far more than the wallet holds
    assert d["action"] == "block" and d["message"].startswith("Sightline BLOCK: would leave less than the 0.01 SOL reserve")
    assert out is None and env.client.sent == []


def test_bad_args_blocked(env):
    d, _ = env.call({"recipient": "nope", "amount": 1})
    assert d["action"] == "block" and "invalid recipient" in d["message"]


def test_hook_crash_fails_closed(env, monkeypatch):
    monkeypatch.setattr(env.gate, "_evaluate_hook", lambda *a: 1 / 0)
    d = env.hook(tool_name="sightline_pay", args={"recipient": DEST, "amount": 1}, session_id="s")
    assert d["action"] == "block" and "ZeroDivisionError" in d["message"]


def test_revoked_grant_stops_cached_allow(env):
    g = env.grant()
    d = env.hook(tool_name="sightline_pay", args={"recipient": DEST, "amount": 0.5}, session_id="s1")
    assert d is None  # hook said ALLOW…
    env.grants.revoke(g.id)  # …then the user revoked before execution
    out = json.loads(env.pay({"recipient": DEST, "amount": 0.5}, session_id="s1"))
    assert out["error"] == "blocked" and env.client.sent == []


def test_parallel_calls_cannot_exceed_cap(env):
    env.grant(cap="1", to=("*",))
    args = [{"recipient": r, "amount": 0.6} for r in (DEST, OTHER)]
    for i, a in enumerate(args):  # both hooks run first and both see room under the cap
        assert env.hook(tool_name="sightline_pay", args=a, session_id=f"p{i}") is None
    results = []
    threads = [threading.Thread(target=lambda a=a, i=i: results.append(
        json.loads(env.pay(a, session_id=f"p{i}")))) for i, a in enumerate(args)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(bool(r.get("sent")) for r in results) == [False, True]
    assert len(env.client.sent) == 1


def test_failed_send_releases_allowance(env, monkeypatch):
    from solana.rpc.core import RPCException

    g = env.grant(cap="1")
    env.client.send_errors = [RPCException("boom")]
    _, out = env.call({"recipient": DEST, "amount": 0.6})
    assert out["error"] == "send_failed"
    assert env.grants.remaining(g) == Decimal(1)
    _, out = env.call({"recipient": DEST, "amount": 0.6})
    assert out["sent"]
