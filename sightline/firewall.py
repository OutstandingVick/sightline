"""Firewall.

``decide(intent, report, settings)`` returns ALLOW, APPROVE or BLOCK.

Order:
  a. Hard blocks — nothing (no grant, no human approval) overrides these:
     failed/incomplete simulation, intent-vs-simulation mismatch, a program outside the
     known-safe set, authority/delegate/close/assign instructions, SOL left below the
     reserve, more than 90% of a token balance in one tx, mainnet without opt-in.
  b. A matching active grant → ALLOW.
  c. Otherwise → APPROVE: a human must confirm this one payment.

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


def hard_blocks(intent, report: SimulationReport, settings) -> Decision | None:
    if settings.network == "mainnet" and not settings.allow_mainnet:
        return _block("mainnet is disabled (set SIGHTLINE_ALLOW_MAINNET=1)", "mainnet")
    if not report.ok:
        return _block(f"simulation failed: {report.error}", "simulation")
    if report.sol_post_lamports is None:
        return _block("simulation did not report the wallet's balance", "simulation")
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
        return _block(f"would leave less than the {Decimal(SOL_RESERVE_LAMPORTS).scaleb(-9)} SOL reserve",
                      "sol_reserve")
    for t in report.token_deltas:
        out, pre = -Decimal(t.delta_ui), Decimal(t.pre_ui)
        if out > 0 and out > pre * MAX_TOKEN_FRACTION:
            return _block(f"spends {out} of {pre} {t.symbol} (over 90% of the balance) in one transaction",
                          "token_fraction")
    return None


def decide(intent, report: SimulationReport, settings, conn=None, now: float | None = None) -> Decision:
    blocked = hard_blocks(intent, report, settings)
    if blocked:
        return blocked
    grant, why = grants.find_matching(intent, settings.network, conn=conn,
                                      now=time.time() if now is None else now)
    if grant is not None:
        return Decision(ALLOW, f"covered by grant {grant.id}", grant.id, f"grant {grant.id}")
    return Decision(APPROVE, why, None, "no_grant")
