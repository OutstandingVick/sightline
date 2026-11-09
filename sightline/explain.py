"""Plain-English explanation of a simulated intent, plus the intent-vs-simulation check.

``mismatches()`` is the part Phase 4's firewall will block on: it compares what the user
asked for (the Intent) with what the simulation says will actually move.
"""

from __future__ import annotations

from decimal import Decimal

from .amounts import from_base_units, to_base_units
from .simulate import SimulationReport, program_label
from .tokens import short


def _sol(lamports: int) -> str:
    return format(from_base_units(lamports, 9).normalize(), "f")


def mismatches(intent, report: SimulationReport) -> list[str]:
    """Differences between the intent and the simulated effects. Empty means they agree."""
    if not report.ok:
        return []
    out: list[str] = []
    amount = Decimal(intent.amount)
    outflow = -report.sol_delta_lamports  # lamports leaving our wallet, fee included

    if intent.kind == "transfer_sol":
        expected = to_base_units(amount, 9) + report.fee_lamports
        if outflow > expected:
            out.append(f"{_sol(outflow)} SOL leaves the wallet; expected {_sol(expected)} (amount + fee)")
        for t in report.token_deltas:
            out.append(f"unexpected token change: {t.delta_ui} {t.symbol}")
    else:
        moved = report.token_delta(intent.mint)
        if moved != -amount:
            out.append(f"{-moved} {intent.symbol or short(intent.mint)} leaves the wallet; expected {amount}")
        for t in report.token_deltas:
            if t.mint != intent.mint:
                out.append(f"unexpected token change: {t.delta_ui} {t.symbol}")
        allowed = report.fee_lamports + report.rent_lamports
        if outflow > allowed:
            out.append(f"{_sol(outflow)} SOL leaves the wallet; expected at most {_sol(allowed)} (fee + rent)")

    if report.recipient_received is not None and Decimal(report.recipient_received) != amount:
        out.append(f"recipient receives {report.recipient_received}; expected {amount}")
    return out


def explain(intent, report: SimulationReport) -> str:
    """1–3 lines a person can read before approving."""
    if not report.ok:
        return f"✗ Simulation failed: {report.error}. Nothing was sent."
    symbol = intent.symbol or short(intent.mint or "")
    lines = [f"You send {Decimal(intent.amount).normalize():f} {symbol} to {short(intent.recipient)}."]
    detail = []
    if report.creates_accounts and intent.kind == "transfer_spl":
        detail.append(f"Creates their {symbol} account (≈{_sol(report.rent_lamports)} SOL rent).")
    elif report.creates_accounts:
        detail.append(f"Creates {len(report.created_accounts)} account(s) (≈{_sol(report.rent_lamports)} SOL rent).")
    detail.append(f"Network fee ≈ {_sol(report.fee_lamports)} SOL.")
    detail.append("Programs: " + ", ".join(dict.fromkeys(program_label(p) for p in report.programs)) + ".")
    lines.append(" ".join(detail))
    if report.unknown_programs:
        lines.append("⚠ Unknown program: " + ", ".join(short(p) for p in report.unknown_programs))
    problems = mismatches(intent, report)
    if problems:
        lines.append("⚠ Mismatch: " + "; ".join(problems))
    return "\n".join(lines)
