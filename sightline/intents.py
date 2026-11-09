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

    def to_dict(self) -> dict:
        return {"summary": self.summary, "sent": True, "signature": self.signature,
                "explorer_url": self.explorer_url, "intent": asdict(self.intent),
                "simulation": self.simulation.to_dict() if self.simulation else None}


class SimulationFailed(WalletError):
    """Simulation rejected the transaction; it was not signed or sent."""

    def __init__(self, preview: Preview):
        super().__init__("simulation_failed", preview.explanation)
        self.preview = preview

    def to_dict(self) -> dict:
        return {"error": self.code, "message": self.message, "sent": False,
                "logs": self.preview.simulation.logs[-5:],
                "simulation": self.preview.simulation.to_dict()}


def pay_intent(wallet: Wallet, recipient: str, amount, token: str | None = "SOL") -> Intent:
    """Validate tool arguments and resolve the token into a concrete Intent."""
    try:
        parse_address(recipient, "recipient")
        value = to_decimal(amount)
        ref = resolve_token(token, wallet.settings.network)
    except (AddressError, AmountError) as exc:
        code = "invalid_amount" if isinstance(exc, AmountError) else "invalid_address"
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
    return built, Preview(intent=intent, simulation=report, explanation=explain(intent, report))


def preview_intent(wallet: Wallet, intent: Intent) -> Preview:
    """Build + simulate + explain. Never signs."""
    return _preview(wallet, intent)[1]


def execute_intent(wallet: Wallet, intent: Intent) -> Receipt:
    built, preview = _preview(wallet, intent)
    if not preview.simulation.ok:
        raise SimulationFailed(preview)
    # Phase 4: firewall verdict(intent, preview.simulation) → allow / approve / block
    signature = wallet.sign_and_send(built)
    settings: Settings = wallet.settings
    return Receipt(intent=intent, signature=signature,
                   explorer_url=settings.explorer_url(signature),
                   summary=preview.explanation, simulation=preview.simulation)
