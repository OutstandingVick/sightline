import pytest
from solders.keypair import Keypair
from solders.pubkey import Pubkey

from fakes import FakeClient
from sightline.config import load_settings
from sightline.intents import Intent, execute_intent, pay_intent
from sightline.wallet import Wallet, WalletError

DEST = str(Keypair().pubkey())


def test_pay_intent_sol(keypair):
    w = Wallet(load_settings(), client=FakeClient())
    assert pay_intent(w, DEST, 0.01) == Intent("transfer_sol", DEST, "0.01", None, 9, "SOL")


def test_pay_intent_spl_by_mint(keypair):
    mint = Pubkey.new_unique()
    w = Wallet(load_settings(), client=FakeClient(mints={mint: 6}))
    i = pay_intent(w, DEST, 1, str(mint))
    assert (i.kind, i.mint, i.decimals) == ("transfer_spl", str(mint), 6)


@pytest.mark.parametrize("to,amount,token,code", [
    ("bad", 1, "SOL", "invalid_address"),
    (DEST, -1, "SOL", "invalid_amount"),
    (DEST, 1, "NOPE", "invalid_address"),
])
def test_pay_intent_rejects(keypair, to, amount, token, code):
    w = Wallet(load_settings(), client=FakeClient())
    with pytest.raises(WalletError) as e:
        pay_intent(w, to, amount, token)
    assert e.value.code == code


def test_execute_intent_receipt(keypair):
    w = Wallet(load_settings(), client=FakeClient())
    r = execute_intent(w, pay_intent(w, DEST, "0.5"))
    assert r.explorer_url == f"https://explorer.solana.com/tx/{r.signature}?cluster=devnet"
    assert r.summary.startswith("You send 0.5 SOL to ") and r.simulation.ok
