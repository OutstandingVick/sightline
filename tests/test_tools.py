import importlib
import json

import pytest
from solders.keypair import Keypair

from fakes import FakeClient

DEST = str(Keypair().pubkey())


@pytest.fixture
def tools(plugin, ctx, keypair, monkeypatch):
    plugin.register(ctx)
    wallet_mod = importlib.import_module(plugin.__name__ + ".sightline.wallet")
    client = FakeClient()
    monkeypatch.setattr(wallet_mod, "Client", lambda *a, **k: client)
    return {n: t["handler"] for n, t in ctx.tools.items()}, client


def test_preview_never_sends(tools):
    handlers, client = tools
    out = json.loads(handlers["sightline_preview"]({"recipient": DEST, "amount": 0.01}))
    assert out["sent"] is False and out["would_succeed"] is True and client.sent == []
    assert out["summary"].startswith("You send 0.01 SOL")
    assert set(out["simulation"]) >= {"ok", "fee_lamports", "sol_delta_lamports", "token_deltas", "programs"}


def test_preview_of_failing_tx(tools):
    handlers, client = tools
    out = json.loads(handlers["sightline_preview"]({"recipient": DEST, "amount": 1e6}))
    assert out["would_succeed"] is False and "Simulation failed" in out["summary"] and client.sent == []


def test_pay_overdraft_is_simulation_failure(tools):
    handlers, client = tools
    out = json.loads(handlers["sightline_pay"]({"recipient": DEST, "amount": 1e6}))
    assert out["error"] == "simulation_failed" and out["sent"] is False and client.sent == []


def test_pay_success_shape(tools, grant_any):
    handlers, client = tools
    out = json.loads(handlers["sightline_pay"]({"recipient": DEST, "amount": 0.01}))
    assert len(client.sent) == 1 and out["simulation"]["ok"] and out["sent"] is True
    assert {"summary", "signature", "explorer_url", "intent", "simulation"} <= set(out)
    assert out["approved_by"] == f"grant {grant_any.id}"
