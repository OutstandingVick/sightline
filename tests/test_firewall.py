from decimal import Decimal
from types import SimpleNamespace as NS

import pytest

from sightline import grants
from sightline.firewall import ALLOW, APPROVE, BLOCK, decide
from sightline.intents import Intent
from sightline.simulate import SimulationReport, TokenDelta

SYSTEM = "11111111111111111111111111111111"
TOKEN = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
ATA = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
USDC = "4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU"
DEST = "7xKqGNm1r5h6tqk3Vb3vKXg6wZ8bq4o5bS2mF8yQ9fP2"
DEVNET = NS(network="devnet", allow_mainnet=False)

SOL = Intent("transfer_sol", DEST, "0.01", None, 9, "SOL")
USD = Intent("transfer_spl", DEST, "1", USDC, 6, "USDC")


def sol_report(**kw):
    base = dict(ok=True, fee_lamports=5000, sol_delta_lamports=-10_005_000, programs=[SYSTEM],
                instructions=["System.Transfer"], recipient_received="0.01", sol_post_lamports=4 * 10**9)
    return SimulationReport(**{**base, **kw})


def usd_report(**kw):
    base = dict(ok=True, fee_lamports=5000, sol_delta_lamports=-2_044_280, programs=[ATA, TOKEN],
                instructions=["Associated Token.CreateIdempotent", "Token.TransferChecked"],
                token_deltas=[TokenDelta(USDC, "USDC", "-1", 6, pre_ui="19")], creates_accounts=True,
                rent_lamports=2_039_280, recipient_received="1", sol_post_lamports=4 * 10**9)
    return SimulationReport(**{**base, **kw})


def grant(token="SOL", cap="1", to=(DEST,)):
    return grants.create(network="devnet", token=token, symbol="SOL", daily_cap=Decimal(cap),
                         max_per_tx=None, recipients=list(to), duration_s=3600)


@pytest.mark.parametrize("report,rule", [
    (sol_report(ok=False, error="insufficient funds"), "simulation"),
    (sol_report(sol_delta_lamports=-90_005_000), "mismatch"),
    (sol_report(programs=[SYSTEM, "Evi1Prog11111111111111111111111111111111111"]), "unknown_program"),
    (sol_report(instructions=["System.Transfer", "System.Assign"]), "forbidden_instruction"),
    (sol_report(instructions=["Token.SetAuthority"]), "forbidden_instruction"),
    (sol_report(instructions=["Token.ApproveChecked"]), "forbidden_instruction"),
    (sol_report(instructions=["Token.CloseAccount"]), "forbidden_instruction"),
    (sol_report(sol_post_lamports=9_999_999), "sol_reserve"),
    (sol_report(sol_post_lamports=None), "simulation"),
])
def test_hard_blocks_beat_grants(report, rule):
    grant(to=("*",), cap="100")
    d = decide(SOL, report, DEVNET)
    assert (d.verdict, d.rule) == (BLOCK, rule)


def test_token_fraction_block():
    grant(token=USDC, cap="100", to=("*",))
    d = decide(USD, usd_report(token_deltas=[TokenDelta(USDC, "USDC", "-1", 6, pre_ui="1.05")]), DEVNET)
    assert (d.verdict, d.rule) == (BLOCK, "token_fraction")


def test_mainnet_without_opt_in():
    assert decide(SOL, sol_report(), NS(network="mainnet", allow_mainnet=False)).rule == "mainnet"


def test_grant_allows():
    g = grant()
    d = decide(SOL, sol_report(), DEVNET)
    assert (d.verdict, d.grant_id, d.rule) == (ALLOW, g.id, f"grant {g.id}")


def test_no_grant_needs_approval_with_reason():
    d = decide(USD, usd_report(), DEVNET)
    assert d.verdict == APPROVE and d.reason == "no grant for USDC on devnet"
    g = grant(token=USDC, cap="0.5")
    d = decide(USD, usd_report(), DEVNET)
    assert d.verdict == APPROVE and f"per-tx max of grant {g.id}" in d.reason


def test_reserve_message_is_readable():
    d = decide(SOL, sol_report(sol_post_lamports=1), DEVNET)
    assert d.reason == "would leave less than the 0.01 SOL reserve"
