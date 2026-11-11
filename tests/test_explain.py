from sightline.explain import explain, mismatches
from sightline.intents import Intent
from sightline.simulate import SimulationReport, TokenDelta, program_label

SYSTEM = "11111111111111111111111111111111"
TOKEN = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
ATA = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
USDC = "4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU"
DEST = "7xKqGNm1r5h6tqk3Vb3vKXg6wZ8bq4o5bS2mF8yQ9fP2"

SOL_INTENT = Intent("transfer_sol", DEST, "0.01", None, 9, "SOL")
USDC_INTENT = Intent("transfer_spl", DEST, "1", USDC, 6, "USDC")


def sol_report(**kw):
    base = dict(ok=True, fee_lamports=5000, sol_delta_lamports=-10_005_000, programs=[SYSTEM],
                recipient_received="0.01")
    return SimulationReport(**{**base, **kw})


def usdc_report(**kw):
    base = dict(ok=True, fee_lamports=5000, sol_delta_lamports=-2_044_280, programs=[ATA, TOKEN],
                token_deltas=[TokenDelta(USDC, "USDC", "-1", 6)], creates_accounts=True,
                created_accounts=["x"], rent_lamports=2_039_280, recipient_received="1")
    return SimulationReport(**{**base, **kw})


def test_sol_explanation():
    assert explain(SOL_INTENT, sol_report()) == (
        "You send 0.01 SOL to 7xKq…9fP2.\nNetwork fee ≈ 0.000005 SOL. Programs: System.")


def test_usdc_explanation_with_ata():
    text = explain(USDC_INTENT, usdc_report())
    assert text.startswith("You send 1 USDC to 7xKq…9fP2.\nCreates their USDC account (≈0.00203928 SOL rent).")
    assert "Programs: Associated Token, Token." in text and "⚠" not in text


def test_no_mismatch_when_consistent():
    assert mismatches(SOL_INTENT, sol_report()) == []
    assert mismatches(USDC_INTENT, usdc_report()) == []


def test_mismatch_more_sol_leaves():
    doctored = sol_report(sol_delta_lamports=-50_005_000)
    assert "⚠ Mismatch: 0.050005 SOL leaves the wallet" in explain(SOL_INTENT, doctored)


def test_mismatch_more_tokens_leave():
    doctored = usdc_report(token_deltas=[TokenDelta(USDC, "USDC", "-5", 6)])
    assert any("5 USDC leaves the wallet; expected 1" in m for m in mismatches(USDC_INTENT, doctored))


def test_mismatch_sol_drained_on_spl_transfer():
    doctored = usdc_report(sol_delta_lamports=-1_000_000_000)
    assert any("expected at most" in m for m in mismatches(USDC_INTENT, doctored))


def test_mismatch_unexpected_token_and_recipient():
    doctored = sol_report(token_deltas=[TokenDelta("M", "M…", "-3", 0)], recipient_received="0.001")
    found = mismatches(SOL_INTENT, doctored)
    assert any("unexpected token change" in m for m in found)
    assert any("recipient receives 0.001" in m for m in found)


def test_unknown_program_flagged():
    evil = "Evi1Prog11111111111111111111111111111111111"
    assert program_label(evil).startswith("unknown Evi1")
    text = explain(SOL_INTENT, sol_report(programs=[SYSTEM, evil], unknown_programs=[evil]))
    assert "unknown Evi1" in text and "⚠ Unknown program: Evi1…1111" in text


def test_failed_report_explanation():
    assert explain(SOL_INTENT, SimulationReport(ok=False, error="insufficient funds")) == (
        "✗ Simulation failed: insufficient funds. Nothing was sent.")


def test_link_label_and_memo_are_shown():
    from dataclasses import replace

    from sightline.explain import explain
    from sightline.intents import Intent
    from sightline.simulate import SimulationReport

    intent = replace(Intent("transfer_sol", "76nKQ7uBMB482NqeVxUjyNXbq2kq741TmbKM9umLTRX1", "0.01", decimals=9,
                            symbol="SOL"), label="Coffee Shop", memo="order-42")
    report = SimulationReport(ok=True, fee_lamports=5000, programs=["11111111111111111111111111111111"],
                              recipient_received="0.01", sol_delta_lamports=-10_005_000)
    text = explain(intent, report)
    assert text.startswith("You send 0.01 SOL to Coffee Shop (76nK…TRX1).") and 'Memo: "order-42".' in text
