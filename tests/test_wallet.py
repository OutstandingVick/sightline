import pytest
from solana.rpc.core import RPCException, TransactionExpiredBlockheightExceededError
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from spl.token.constants import ASSOCIATED_TOKEN_PROGRAM_ID

from fakes import FakeClient
from sightline.config import load_settings
from sightline.wallet import Wallet, WalletError

DEST = str(Keypair().pubkey())


@pytest.fixture
def wallet(keypair):
    return lambda **kw: Wallet(load_settings(), client=FakeClient(**kw))


def test_sol_transfer_is_unsigned_v0(wallet):
    built = wallet().build_sol_transfer(DEST, 0.01)
    assert built.tx.signatures[0] == built.tx.signatures[0].default()
    assert "0.01 SOL" in built.summary


def test_insufficient_sol(wallet):
    with pytest.raises(WalletError) as e:
        wallet(lamports=1000).build_sol_transfer(DEST, 1)
    assert e.value.code == "insufficient_funds"


def test_invalid_recipient(wallet):
    with pytest.raises(WalletError) as e:
        wallet().build_sol_transfer("nope", 1)
    assert e.value.code == "invalid_address"


def test_spl_transfer_creates_ata_idempotently(wallet):
    mint = Pubkey.new_unique()
    w = wallet(mints={mint: 6}, token_balance=5_000_000)
    built = w.build_spl_transfer(DEST, mint, "1.5")
    programs = [built.tx.message.account_keys[ix.program_id_index] for ix in built.tx.message.instructions]
    assert programs[0] == ASSOCIATED_TOKEN_PROGRAM_ID
    assert bytes(built.tx.message.instructions[0].data) == b"\x01"  # CreateIdempotent
    assert bytes(built.tx.message.instructions[1].data)[0] == 12  # TransferChecked


def test_spl_insufficient(wallet):
    mint = Pubkey.new_unique()
    with pytest.raises(WalletError) as e:
        wallet(mints={mint: 6}, token_balance=10).build_spl_transfer(DEST, mint, 1)
    assert e.value.code == "insufficient_funds"


def test_spl_unknown_mint(wallet):
    with pytest.raises(WalletError) as e:
        wallet().build_spl_transfer(DEST, Pubkey.new_unique(), 1)
    assert e.value.code == "unknown_mint"


def test_sign_and_send_signs_with_wallet(wallet, keypair):
    w = wallet()
    sig = w.sign_and_send(w.build_sol_transfer(DEST, 0.01))
    assert sig and w.client.sent[0].message.account_keys[0] == keypair.pubkey()
    assert w.client.sent[0].verify_with_results() == [True]


def test_blockhash_expiry_rebuilds_once(wallet):
    w = wallet()
    w.client.confirm_errors = [TransactionExpiredBlockheightExceededError("x")]
    built = w.build_sol_transfer(DEST, 0.01)
    w.sign_and_send(built)
    assert len(w.client.sent) == 2 and w.client.blockhashes == 2


def test_blockhash_expiry_twice_fails(wallet):
    w = wallet()
    w.client.confirm_errors = [TransactionExpiredBlockheightExceededError("x")] * 2
    with pytest.raises(WalletError) as e:
        w.sign_and_send(w.build_sol_transfer(DEST, 0.01))
    assert e.value.code == "blockhash_expired"


def test_send_insufficient_funds_mapped(wallet):
    w = wallet()
    w.client.send_errors = [RPCException("Transfer: insufficient lamports 5, need 10")]
    with pytest.raises(WalletError) as e:
        w.sign_and_send(w.build_sol_transfer(DEST, 0.01))
    assert e.value.code == "insufficient_funds"


def test_rpc_timeout_mapped(wallet):
    import httpx

    w = wallet()
    w.client.send_errors = [httpx.ReadTimeout("slow")]
    with pytest.raises(WalletError) as e:
        w.sign_and_send(w.build_sol_transfer(DEST, 0.01))
    assert e.value.code == "rpc_timeout"


def test_balances(wallet):
    usdc = "4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU"
    other = str(Pubkey.new_unique())
    accs = [{"mint": usdc, "tokenAmount": {"amount": "2500000", "decimals": 6}},
            {"mint": other, "tokenAmount": {"amount": "7", "decimals": 0}}]
    out = wallet(lamports=1_500_000_000, token_accounts=accs).get_balances()
    assert out["sol"] == "1.5"
    assert {"mint": usdc, "symbol": "USDC", "amount": "2.5", "decimals": 6} in out["tokens"]
    assert any(t["symbol"].startswith(other[:4]) and "…" in t["symbol"] for t in out["tokens"])
