"""Intents: the single choke point between tools and the wallet.

Every value-moving tool turns its arguments into an ``Intent`` and calls
``execute_intent``: build → simulate → (Phase 4: firewall) → sign_and_send.
Simulation failure or an RPC error means nothing is sent (fail closed).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .amounts import AmountError, format_amount, to_decimal
from .config import Settings
from .explain import explain
from .simulate import SimulationReport, simulate
from .tokens import AddressError, parse_address, resolve_token
from .wallet import Wallet, WalletError


@dataclass(frozen=True)
class Intent:
    kind: str  # "transfer_sol" | "transfer_spl"
    recipient: str
    amount: str  # Decimal as string: exact, JSON-safe
    mint: str | None = None
    decimals: int | None = None
    symbol: str | None = None


@dataclass(frozen=True)
class Preview:
    intent: Intent
    simulation: SimulationReport
    explanation: str

    def to_dict(self) -> dict:
        return {"summary": self.explanation, "would_succeed": self.simulation.ok, "sent": False,
                "intent": asdict(self.intent), "simulation": self.simulation.to_dict()}


@dataclass(frozen=True)
class Receipt:
    intent: Intent
    signature: str
    explorer_url: str
    summary: str
    simulation: SimulationReport | None = None  # what was approved; Phase 4 firewall input
    approved_by: str = ""  # "grant g_xxxx" or "human"

    def to_dict(self) -> dict:
        return {"summary": self.summary, "sent": True, "approved_by": self.approved_by,
                "signature": self.signature,
                "explorer_url": self.explorer_url, "intent": asdict(self.intent),
                "simulation": self.simulation.to_dict() if self.simulation else None}


class Blocked(WalletError):
    """The firewall refused this payment; nothing was signed or sent."""

    def __init__(self, decision, preview: "Preview"):
        super().__init__("blocked", f"Sightline BLOCK: {decision.reason}\n{preview.explanation}")
        self.decision = decision
        self.preview = preview

    def to_dict(self) -> dict:
        from .messages import rule_step

        return {"error": self.code, "message": self.message, "sent": False,
                "next_step": rule_step(self.decision.rule) or "Nothing was sent.",
                "decision": self.decision.to_dict(), "simulation": self.preview.simulation.to_dict()}


class SimulationFailed(WalletError):
    """Simulation rejected the transaction; it was not signed or sent."""

    def __init__(self, preview: Preview):
        super().__init__(preview.simulation.error_code or "simulation_failed", preview.explanation)
        self.preview = preview

    def to_dict(self) -> dict:
        from .messages import next_step

        return {"error": self.code, "message": self.message, "sent": False,
                "next_step": next_step(self.code),
                "logs": self.preview.simulation.logs[-5:],
                "simulation": self.preview.simulation.to_dict()}


def pay_intent(wallet: Wallet, recipient: str, amount, token: str | None = "SOL") -> Intent:
    """Validate tool arguments and resolve the token into a concrete Intent."""
    try:
        parse_address(recipient, "recipient")
        value = to_decimal(amount)
        ref = resolve_token(token, wallet.settings.network)
    except (AddressError, AmountError) as exc:
        code = getattr(exc, "code", None) or ("invalid_amount" if isinstance(exc, AmountError) else "invalid_address")
        raise WalletError(code, str(exc)) from None
    if ref.native:
        return Intent(kind="transfer_sol", recipient=recipient.strip(), amount=format_amount(value),
                      decimals=9, symbol="SOL")
    mint = wallet.get_mint(ref.mint)
    return Intent(kind="transfer_spl", recipient=recipient.strip(), amount=format_amount(value),
                  mint=str(ref.mint), decimals=mint.decimals, symbol=ref.symbol)


def build(wallet: Wallet, intent: Intent):
    if intent.kind == "transfer_sol":
        return wallet.build_sol_transfer(intent.recipient, intent.amount)
    if intent.kind == "transfer_spl":
        return wallet.build_spl_transfer(intent.recipient, intent.mint, intent.amount)
    raise WalletError("unsupported_intent", f"unsupported intent {intent.kind!r}")


def _preview(wallet: Wallet, intent: Intent):
    built = build(wallet, intent)
    report = simulate(wallet, built, recipient=intent.recipient)
    text = explain(intent, report)
    if wallet.settings.network == "mainnet":
        text = "⚠ MAINNET — real funds. " + text
    return built, Preview(intent=intent, simulation=report, explanation=text)


def preview_intent(wallet: Wallet, intent: Intent) -> Preview:
    """Build + simulate + explain. Never signs."""
    return _preview(wallet, intent)[1]


def execute_intent(wallet: Wallet, intent: Intent, evaluation=None) -> Receipt:
    """Second gate + send. ``evaluation`` is the hook's cached result for this exact call.

    The firewall is re-run here regardless of what the hook said. ALLOW reserves spend
    against the grant atomically (same transaction as the cap check). APPROVE proceeds
    only if the hook asked a human about this call (Hermes runs the tool only after a
    yes); without that evidence it is a BLOCK.
    """
    from . import audit
    from .db import transaction
    from .firewall import ALLOW, APPROVE, BLOCK, Decision, decide
    from .gate import log_decision

    if evaluation is not None and evaluation.intent == intent:
        built, preview = evaluation.built, evaluation.preview
        hook_verdict = evaluation.decision.verdict
    else:
        built, preview = _preview(wallet, intent)
        hook_verdict = None
    report = preview.simulation
    settings: Settings = wallet.settings
    intent_d = asdict(intent)

    refusal = None
    with transaction() as conn:
        decision = decide(intent, report, settings, conn=conn)
        if decision.verdict == APPROVE and hook_verdict != APPROVE:
            decision = Decision(BLOCK, f"needs human approval ({decision.reason}) but none was given",
                                None, "approval_missing")
        log_decision(intent_d, decision, preview.explanation, "execute", conn=conn)
        if decision.verdict == BLOCK:
            refusal = decision
        else:
            approval = "grant" if decision.verdict == ALLOW else "human"
            seq = audit.append("execute", {
                "intent": intent_d, "grant_id": decision.grant_id, "approval": approval,
                "amount": intent.amount, "token": "SOL" if intent.kind == "transfer_sol" else intent.mint,
                "explanation": preview.explanation,
                "simulation": {k: report.to_dict()[k] for k in (
                    "fee_lamports", "sol_delta_lamports", "token_deltas", "programs", "slot")},
            }, conn=conn)
    if refusal is not None:
        if not report.ok:
            raise SimulationFailed(preview)
        raise Blocked(refusal, preview)

    try:
        signature = wallet.sign_and_send(built)
    except Exception as exc:  # release the reserved spend; re-raise for the tool layer
        audit.append("failed", {"ref": seq, "error": getattr(exc, "code", type(exc).__name__),
                                "message": getattr(exc, "message", "")})
        raise
    audit.append("sent", {"ref": seq, "signature": signature, "explorer_url": settings.explorer_url(signature)})
    return Receipt(intent=intent, signature=signature,
                   explorer_url=settings.explorer_url(signature),
                   summary=preview.explanation, simulation=report,
                   approved_by=f"grant {decision.grant_id}" if decision.verdict == ALLOW else "human")
