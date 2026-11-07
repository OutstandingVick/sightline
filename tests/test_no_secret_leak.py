"""The secret key must never appear in any tool output, success or failure."""

import json
import importlib

import pytest
from solders.keypair import Keypair

from fakes import FakeClient

DEST = str(Keypair().pubkey())


@pytest.fixture
def tools(plugin, ctx, keypair, monkeypatch):
    plugin.register(ctx)
    wallet_mod = importlib.import_module(plugin.__name__ + ".sightline.wallet")
    monkeypatch.setattr(wallet_mod, "Client", lambda *a, **k: FakeClient())
    tools = {n: t["handler"] for n, t in ctx.tools.items()}
    tools["_schemas"] = {n: t["schema"] for n, t in ctx.tools.items()}
    return tools


CALLS = [
    ("sightline_status", {}),
    ("sightline_balance", {}),
    ("sightline_pay", {"recipient": DEST, "amount": 0.01}),
    ("sightline_pay", {"recipient": "garbage", "amount": 1}),
    ("sightline_pay", {"recipient": DEST, "amount": 1e9}),
    ("sightline_pay", {"recipient": DEST, "amount": 1, "token": "WHAT"}),
]


@pytest.mark.parametrize("name,args", CALLS)
def test_outputs_never_contain_secret(tools, keypair, name, args):
    raw = tools[name](args)
    json.loads(raw)
    secret = str(keypair)
    assert secret not in raw
    assert secret[:20] not in raw


def test_secret_errors_do_not_echo(tools, monkeypatch):
    monkeypatch.setenv("SIGHTLINE_SECRET_KEY", "my-super-secret-not-base58!")
    for name, args in CALLS:
        assert not name.startswith("_")
        assert "my-super-secret" not in tools[name](args)


def test_no_raw_transaction_tools(tools):
    for name, schema in tools["_schemas"].items():
        params = set(schema["parameters"]["properties"])
        assert not params & {"transaction", "tx", "instructions", "raw", "serialized"}, name
