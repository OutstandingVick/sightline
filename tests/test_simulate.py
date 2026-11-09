
import pytest
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from spl.token.instructions import get_associated_token_address

from fakes import ATA_RENT, FEE, FakeClient
from sightline.config import load_settings
from sightline.intents import execute_intent, pay_intent, preview_intent
from sightline.simulate import simulate
from sightline.wallet import Wallet

DEST = Keypair().pubkey()


@pytest.fixture
def setup(keypair, cluster):
    mint = Pubkey.new_unique()
    owner = keypair.pubkey()
    src = get_associated_token_address(owner, mint)
    cluster.tokens[str(src)] = {"mint": str(mint), "owner": str(owner), "amount": 5_000_000, "decimals": 6}
    cluster.lamports[str(src)] = ATA_RENT
    w = Wallet(load_settings(), client=FakeClient(mints={mint: 6}))
    return w, mint


def test_sol_transfer_diff(setup):
    w, _ = setup
    r = simulate(w, w.build_sol_transfer(str(DEST), "0.01"), recipient=str(DEST))
    assert r.ok and r.sol_delta_lamports == -(10_000_000 + FEE) and r.fee_lamports == FEE
    assert r.token_deltas == [] and r.recipient_received == "0.01" and not r.creates_accounts
    assert r.programs == ["11111111111111111111111111111111"] and r.unknown_programs == []
    assert str(w.owner) in r.writable_accounts and str(DEST) in r.writable_accounts


def test_spl_transfer_diff_existing_ata(setup, cluster):
    w, mint = setup
    dest_ata = get_associated_token_address(DEST, mint)
    cluster.tokens[str(dest_ata)] = {"mint": str(mint), "owner": str(DEST), "amount": 0, "decimals": 6}
    cluster.lamports[str(dest_ata)] = ATA_RENT
    r = simulate(w, w.build_spl_transfer(str(DEST), mint, "1.5"), recipient=str(DEST))
    assert r.ok and not r.creates_accounts and r.sol_delta_lamports == -FEE
    assert [(t.mint, t.delta_ui, t.decimals) for t in r.token_deltas] == [(str(mint), "-1.5", 6)]
    assert r.recipient_received == "1.5"


def test_spl_transfer_creates_ata(setup):
    w, mint = setup
    p = preview_intent(w, pay_intent(w, str(DEST), 1, str(mint)))
    r = p.simulation
    assert r.ok and r.creates_accounts and r.rent_lamports == ATA_RENT
    assert r.created_accounts == [str(get_associated_token_address(DEST, mint))]
    assert r.sol_delta_lamports == -(FEE + ATA_RENT)
    assert "Creates their" in p.explanation and "0.00203928 SOL rent" in p.explanation
    assert "Programs: Associated Token, Token." in p.explanation and "Mismatch" not in p.explanation


def test_simulation_error_sends_nothing(setup, monkeypatch):
    w, _ = setup
    sent = []
    monkeypatch.setattr(w, "sign_and_send", lambda built: sent.append(built) or "SIG")
    from sightline.intents import SimulationFailed

    with pytest.raises(SimulationFailed) as e:
        execute_intent(w, pay_intent(w, str(DEST), 1_000))  # far more than the 10 SOL balance
    assert sent == [] and e.value.preview.simulation.error == "insufficient funds"
    d = e.value.to_dict()
    assert d["sent"] is False and d["logs"] and "Nothing was sent" in d["message"]


def test_rpc_exception_sends_nothing(setup, cluster, monkeypatch):
    import httpx

    w, _ = setup
    cluster.raise_exc = httpx.ConnectTimeout("down")
    sent = []
    monkeypatch.setattr(w, "sign_and_send", lambda built: sent.append(built) or "SIG")
    from sightline.intents import SimulationFailed

    with pytest.raises(SimulationFailed) as e:
        execute_intent(w, pay_intent(w, str(DEST), "0.01"))
    assert sent == [] and "simulation RPC failed" in e.value.preview.simulation.error


def test_missing_balance_fields_fail_closed(setup, cluster):
    w, _ = setup
    cluster.override = {"preTokenBalances": None}
    del_fields = simulate(w, w.build_sol_transfer(str(DEST), "0.01"))
    assert not del_fields.ok


def test_successful_pay_returns_explanation(setup):
    w, _ = setup
    r = execute_intent(w, pay_intent(w, str(DEST), "0.01"))
    assert r.summary.splitlines()[0] == f"You send 0.01 SOL to {str(DEST)[:4]}…{str(DEST)[-4:]}."
    assert "Network fee ≈ 0.000005 SOL. Programs: System." in r.summary
    assert r.simulation.ok and r.explorer_url.endswith("?cluster=devnet")


def test_report_round_trips_through_dict(setup):
    from sightline.simulate import SimulationReport

    w, mint = setup
    r = simulate(w, w.build_spl_transfer(str(DEST), mint, 1), recipient=str(DEST))
    assert SimulationReport.from_dict(r.to_dict()) == r
