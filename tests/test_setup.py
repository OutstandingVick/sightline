"""First-run setup: create/keep the wallet, store it, fund it, never print the secret."""

from types import SimpleNamespace as NS

import pytest

import sightline.setup  # noqa: F401
from sightline import setup


class Faucet:
    def __init__(self, fail_times=0, balance=0, rate_limited=True):
        self.fail_times, self.balance, self.rate_limited = fail_times, balance, rate_limited
        self.requests = 0

    def request_airdrop(self, pubkey, lamports):
        self.requests += 1
        if self.requests <= self.fail_times:
            raise RuntimeError("429 Too Many Requests" if self.rate_limited else "boom")
        self.balance += lamports

    def get_balance(self, pubkey):
        return NS(value=self.balance)


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("SIGHTLINE_SECRET_KEY", raising=False)
    monkeypatch.delenv("SIGHTLINE_RPC_URL", raising=False)
    return tmp_path


def test_creates_stores_and_funds(home):
    faucet = Faucet()
    lines = setup.run(client=faucet, sleep=lambda s: None)
    env = (home / ".env").read_text()
    secret = env.split("SIGHTLINE_SECRET_KEY=")[1].strip()
    assert "Created a new devnet wallet" in lines[0]
    assert all(secret not in line for line in lines)  # never shown
    assert any("Received 1 devnet SOL" in line for line in lines)
    assert oct((home / ".env").stat().st_mode)[-3:] == "600"


def test_keeps_existing_wallet(home, keypair):
    lines = setup.run(client=Faucet(balance=10**9), sleep=lambda s: None)
    assert lines[0] == f"✓ Wallet already configured: {keypair.pubkey()}"
    assert any("already funded" in line for line in lines)
    assert not (home / ".env").exists()


def test_refuses_to_touch_invalid_key(home, monkeypatch):
    monkeypatch.setenv("SIGHTLINE_SECRET_KEY", "not-a-key")
    lines = setup.run(client=Faucet(), sleep=lambda s: None)
    assert lines[0].startswith("✗") and "Not changing it" in lines[1]


def test_retries_then_succeeds(home):
    waits = []
    faucet = Faucet(fail_times=2)
    lines = setup.run(client=faucet, sleep=waits.append)
    assert faucet.requests == 3 and waits[:2] == [2, 5]
    assert any("attempt 3" in line for line in lines)


def test_rate_limited_prints_faucets(home):
    lines = setup.run(client=Faucet(fail_times=99), sleep=lambda s: None)
    text = "\n".join(lines)
    assert "rate limited" in text and "https://faucet.solana.com" in text and "address:" in text


def test_mainnet_has_no_faucet(home, monkeypatch, keypair):
    monkeypatch.setenv("SIGHTLINE_RPC_URL", "https://api.mainnet-beta.solana.com")
    lines = setup.run(client=Faucet(), sleep=lambda s: None)
    assert "MAINNET: no faucet" in lines[-1]


def test_rpc_down(home):
    class Down(Faucet):
        def get_balance(self, pubkey):
            raise ConnectionError("down")

    lines = setup.run(client=Down(), sleep=lambda s: None)
    assert "Could not reach the Solana RPC" in lines[-1]


def test_slash_command(home, monkeypatch):
    from sightline import commands

    out = commands.handle("setup --no-airdrop")
    assert "Created a new devnet wallet" in out and "SIGHTLINE_SECRET_KEY" in out


def test_refused_faucet_stops_retrying_and_says_why(home):
    import httpx

    class Gone(Faucet):
        def request_airdrop(self, pubkey, lamports):
            self.requests += 1
            req = httpx.Request("POST", "https://api.devnet.solana.com")
            try:
                raise httpx.HTTPStatusError("410", request=req, response=httpx.Response(410, request=req))
            except httpx.HTTPStatusError as cause:
                raise RuntimeError("HTTPStatusError raised in RequestAirdrop") from cause

    faucet = Gone()
    lines = setup.run(client=faucet, sleep=lambda s: None)
    assert faucet.requests == 1
    assert any("HTTP 410" in line for line in lines) and any("faucet.solana.com" in line for line in lines)


def test_setup_prints_the_readme_faucets(home):
    from sightline.messages import FAUCET_URLS

    text = "\n".join(setup.run(client=Faucet(fail_times=99), sleep=lambda s: None))
    assert all(url in text for url in FAUCET_URLS) and "GitHub" in text
    assert "sends are blocked until the wallet is funded" in text
    readme = (__import__("pathlib").Path(__file__).resolve().parents[1] / "README.md").read_text()
    assert all(url in readme for url in FAUCET_URLS)  # README and setup list the same faucets
