"""Firewall.

``decide(intent, report, settings)`` returns ALLOW, APPROVE or BLOCK.

Order (policy first, so its reason is never hidden behind a funding problem):
  1. Policy blocks that need no simulation: mainnet without opt-in; a drain (the request
     is for the whole balance, or would leave less than the SOL reserve).
  2. Grant lookup (policy verdict: covered by grant X / why no grant covers it).
  3. Simulation failed or incomplete → BLOCK (fail closed). The reason states the policy
     verdict from step 2 first, then the funding/simulation problem.
  4. Simulation-based hard blocks: unknown program, forbidden instruction, mismatch,
     SOL reserve, more than 90% of a token balance.
  5. Grant → ALLOW, otherwise APPROVE (a human confirms this one payment).

Call ``decide`` inside ``db.transaction`` when the verdict is used to reserve spend, so
two concurrent payments can't both fit under the same cap.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from decimal import Decimal

from . import grants
from .explain import mismatches
from .simulate import PROGRAM_NAMES, SimulationReport

ALLOW, APPROVE, BLOCK = "ALLOW", "APPROVE", "BLOCK"

SAFE_PROGRAMS = frozenset(PROGRAM_NAMES)
FORBIDDEN_INSTRUCTIONS = frozenset({
    "Token.Approve", "Token.ApproveChecked", "Token.SetAuthority", "Token.CloseAccount",
    "Token-2022.Approve", "Token-2022.ApproveChecked", "Token-2022.SetAuthority", "Token-2022.CloseAccount",
    "System.Assign", "System.AssignWithSeed", "System.AuthorizeNonceAccount", "System.WithdrawNonceAccount",
})
SOL_RESERVE_LAMPORTS = 10_000_000  # 0.01 SOL stays in the wallet for fees
MAX_TOKEN_FRACTION = Decimal("0.9")


@dataclass(frozen=True)
class Decision:
    verdict: str
    reason: str
    grant_id: str | None
    rule: str

    def to_dict(self) -> dict:
        return asdict(self)


def _block(reason: str, rule: str) -> Decision:
    return Decision(BLOCK, reason, None, rule)


def _reserve_text() -> str:
    return format(Decimal(SOL_RESERVE_LAMPORTS).scaleb(-9).normalize(), "f")


def _lamports(amount: str) -> int:
    return int(Decimal(amount).scaleb(9))


def policy_blocks(intent, settings, balance_lamports: int | None = None) -> Decision | None:
    """Blocks decided from the request alone (plus the current balance), before simulation."""
    if settings.network == "mainnet" and not settings.allow_mainnet:
        return _block("mainnet is disabled (set SIGHTLINE_ALLOW_MAINNET=1)", "mainnet")
    symbol = intent.symbol or "token"
    if getattr(intent, "drain", False):
        return _block(f"asks to send the entire {symbol} balance; Sightline never empties the wallet "
                      f"(it keeps {_reserve_text()} SOL for fees)", "drain")
    if intent.kind == "transfer_sol" and balance_lamports:
        if _lamports(intent.amount) + SOL_RESERVE_LAMPORTS > balance_lamports:
            return _block(f"would leave less than the {_reserve_text()} SOL reserve "
                          f"(wallet holds {format(Decimal(balance_lamports).scaleb(-9).normalize(), 'f')} SOL)",
                          "sol_reserve")
    return None


def funding_note(report: SimulationReport, balance_lamports: int | None) -> str:
    """The non-policy problem behind a failed simulation, in words."""
    if report.error_code in ("empty_wallet", "insufficient_funds"):
        held = "0" if report.error_code == "empty_wallet" or not balance_lamports else \
            format(Decimal(balance_lamports).scaleb(-9).normalize(), "f")
        return f"wallet has {held} SOL — run `hermes sightline setup` for funding options"
    if report.error_code == "insufficient_token":
        return "wallet holds less of this token than requested"
    return f"simulation failed: {report.error}"


def hard_blocks(intent, report: SimulationReport, settings) -> Decision | None:
    """Simulation-based hard blocks (call only with a successful, complete simulation)."""
    bad = [p for p in report.programs if p not in SAFE_PROGRAMS]
    if bad:
        return _block(f"calls a program outside the safe set: {', '.join(bad)}", "unknown_program")
    forbidden = [k for k in report.instructions if k in FORBIDDEN_INSTRUCTIONS or k.endswith(".Unknown")]
    if forbidden:
        return _block(f"forbidden instruction: {', '.join(forbidden)}", "forbidden_instruction")
    problems = mismatches(intent, report)
    if problems:
        return _block("simulation does not match the request: " + "; ".join(problems), "mismatch")
    if report.sol_post_lamports < SOL_RESERVE_LAMPORTS:
        return _block(f"would leave less than the {_reserve_text()} SOL reserve", "sol_reserve")
    for t in report.token_deltas:
        out, pre = -Decimal(t.delta_ui), Decimal(t.pre_ui)
        if out > 0 and out > pre * MAX_TOKEN_FRACTION:
            return _block(f"spends {out} of {pre} {t.symbol} (over 90% of the balance) in one transaction",
                          "token_fraction")
    return None


def decide(intent, report: SimulationReport, settings, conn=None, now: float | None = None,
           balance_lamports: int | None = None) -> Decision:
    if balance_lamports is None:
        balance_lamports = report.sol_pre_lamports
    blocked = policy_blocks(intent, settings, balance_lamports)
    if blocked:
        return blocked
    grant, why = grants.find_matching(intent, settings.network, conn=conn,
                                      now=time.time() if now is None else now)
    if not report.ok or report.sol_post_lamports is None:
        problem = funding_note(report, balance_lamports) if not report.ok else \
            "simulation did not report the wallet's balance"
        if grant is not None:
            return Decision(BLOCK, f"covered by grant {grant.id}, but {problem}", grant.id, "simulation")
        return Decision(BLOCK, f"no grant covers this: {why}. (Also: {problem}.)", None, "no_grant")
    blocked = hard_blocks(intent, report, settings)
    if blocked:
        return blocked
    if grant is not None:
        return Decision(ALLOW, f"covered by grant {grant.id}", grant.id, f"grant {grant.id}")
    return Decision(APPROVE, why, None, "no_grant")
