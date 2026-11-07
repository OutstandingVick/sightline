"""Opt-in live test: SIGHTLINE_LIVE_TESTS=1 with a funded SIGHTLINE_SECRET_KEY on devnet."""

import os

import pytest
from solders.keypair import Keypair
from solders.pubkey import Pubkey

from sightline.config import load_settings
from sightline.intents import execute_intent, pay_intent
from sightline.wallet import Wallet

pytestmark = pytest.mark.skipif(os.environ.get("SIGHTLINE_LIVE_TESTS") != "1",
                                reason="set SIGHTLINE_LIVE_TESTS=1 to hit devnet")


def test_send_0_001_sol_on_devnet():
    settings = load_settings()
    assert settings.network == "devnet", "live tests only run on devnet"
    w = Wallet(settings)
    dest = str(Keypair().pubkey())
    receipt = execute_intent(w, pay_intent(w, dest, "0.001"))
    print(f"\nlive signature: {receipt.signature}\n{receipt.explorer_url}")
    assert w.client.get_balance(Pubkey.from_string(dest)).value == 1_000_000
