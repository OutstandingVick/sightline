"""Every failure a newcomer can hit returns a code, a plain message and a next step — never a traceback."""

import importlib
import json

import pytest
from fakes import FakeClient
from solders.keypair import Keypair

import sightline.grants  # noqa: F401  (import before fixtures, like the other test modules)

DEST = str(Keypair().pubkey())


@pytest.fixture
def run(plugin, ctx, keypair, monkeypatch):
    plugin.register(ctx)
    wallet_mod = importlib.import_module(plugin.__name__ + ".sightline.wallet")
    holder = {"client": FakeClient()}
    monkeypatch.setattr(wallet_mod, "Client", lambda *a, **k: holder["client"])

    def call(tool, **args):
        raw = ctx.tools[tool]["handler"](args)
        assert "Traceback" not in raw and "File \"" not in raw
        return json.loads(raw)

    call.holder = holder
    return call


def friendly(out, code):
    assert out["error"] == code, out
    assert out["message"] and out["next_step"], out
    return out


def test_missing_secret(run, monkeypatch):
    monkeypatch.delenv("SIGHTLINE_SECRET_KEY")
    out = friendly(run("sightline_balance"), "missing_secret")
    assert "/sightline setup" in out["next_step"]


def test_invalid_secret(run, monkeypatch):
    monkeypatch.setenv("SIGHTLINE_SECRET_KEY", "hunter2")
    out = friendly(run("sightline_status"), "invalid_secret")
    assert "hunter2" not in json.dumps(out)


def test_json_array_secret_is_accepted(run, monkeypatch, keypair):
    monkeypatch.setenv("SIGHTLINE_SECRET_KEY", json.dumps(list(bytes(keypair))))
    assert run("sightline_status")["public_key"] == str(keypair.pubkey())


def test_mainnet_without_opt_in(run, monkeypatch):
    monkeypatch.setenv("SIGHTLINE_RPC_URL", "https://api.mainnet-beta.solana.com")
    out = friendly(run("sightline_balance"), "mainnet_refused")
    assert "MAINNET" in out["message"] and "SIGHTLINE_ALLOW_MAINNET=1" in out["next_step"]


def test_rpc_down_on_balance(run):
    class Down(FakeClient):
        def get_balance(self, *a, **k):
            import httpx

            raise httpx.ConnectError("connection refused")

    run.holder["client"] = Down()
    out = run("sightline_balance")
    assert out["error"] in ("rpc_error", "rpc_timeout") and out["next_step"]


def test_rpc_timeout_on_pay(run, cluster, grant_any):
    import httpx

    cluster.raise_exc = httpx.ReadTimeout("slow")
    out = friendly(run("sightline_pay", recipient=DEST, amount=0.01), "rpc_timeout")
    assert out["sent"] is False


def test_invalid_recipient(run):
    friendly(run("sightline_pay", recipient="not-an-address", amount=0.01), "invalid_address")


def test_unknown_token(run):
    out = friendly(run("sightline_preview", recipient=DEST, amount=1, token="DOGE"), "unknown_token")
    assert "USDC" in out["message"]


def test_invalid_amount(run):
    friendly(run("sightline_preview", recipient=DEST, amount=-1), "invalid_amount")


def test_empty_wallet(run, cluster, grant_any):
    cluster.raise_exc = None
    cluster.payer_lamports = 0
    run.holder["client"] = FakeClient(lamports=0)
    out = run("sightline_pay", recipient=DEST, amount=0.01)
    assert out["error"] in ("insufficient_funds", "empty_wallet") and "faucet" in out["next_step"]


def test_insufficient_token_balance(run, cluster, keypair):
    from solders.pubkey import Pubkey
    from spl.token.instructions import get_associated_token_address

    mint = Pubkey.new_unique()
    src = get_associated_token_address(keypair.pubkey(), mint)
    cluster.tokens[str(src)] = {"mint": str(mint), "owner": str(keypair.pubkey()), "amount": 1_000_000, "decimals": 6}
    run.holder["client"] = FakeClient(mints={mint: 6})
    out = friendly(run("sightline_preview", recipient=DEST, amount=5, token=str(mint)), "insufficient_token")
    assert out["would_succeed"] is False


def test_expired_blockhash(run, grant_any):
    from solana.rpc.core import RPCException

    run.holder["client"].send_errors = [RPCException("Blockhash not found")] * 2
    out = friendly(run("sightline_pay", recipient=DEST, amount=0.01), "blockhash_expired")
    assert "Nothing was sent" in out["next_step"]


def test_block_has_next_step(run, grant_any):
    out = run("sightline_pay", recipient=DEST, amount=9.995)  # the fake cluster holds 10 SOL: would leave < 0.01
    assert out["error"] == "blocked" and "0.01 SOL" in out["next_step"]


def test_no_grant_without_hook_says_what_to_do(run):
    out = run("sightline_pay", recipient=DEST, amount=0.01)
    assert out["error"] == "blocked" and out["next_step"]


def test_mainnet_opt_in_says_mainnet_everywhere(run, monkeypatch):
    monkeypatch.setenv("SIGHTLINE_RPC_URL", "https://api.mainnet-beta.solana.com")
    monkeypatch.setenv("SIGHTLINE_ALLOW_MAINNET", "1")

    class Mainnet(FakeClient):
        def get_genesis_hash(self):
            from types import SimpleNamespace as NS

            return NS(value="5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d")

    run.holder["client"] = Mainnet()
    assert "MAINNET" in run("sightline_status")["warning"]
    assert "MAINNET" in run("sightline_balance")["warning"]
    assert run("sightline_preview", recipient=DEST, amount=0.01)["summary"].startswith("⚠ MAINNET")
