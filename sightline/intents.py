"""Intents: the single choke point between tools and the wallet.

Every value-moving tool turns its arguments into an ``Intent`` and calls
``execute_intent``. Phase 2 adds simulation and Phase 4 the firewall here,
between ``build`` and ``sign_and_send``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .amounts import AmountError, format_amount, to_decimal
from .config import Settings
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
class Receipt:
    intent: Intent
    signature: str
    explorer_url: str
    summary: str

    def to_dict(self) -> dict:
        return {"summary": self.summary, "signature": self.signature,
                "explorer_url": self.explorer_url, "intent": asdict(self.intent)}


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


def execute_intent(wallet: Wallet, intent: Intent) -> Receipt:
    built = build(wallet, intent)
    # Phase 2: simulate(built) → explanation
    # Phase 4: firewall verdict(intent, simulation) → allow / approve / block
    signature = wallet.sign_and_send(built)
    settings: Settings = wallet.settings
    return Receipt(intent=intent, signature=signature,
                   explorer_url=settings.explorer_url(signature),
                   summary=f"Sent: {built.summary} on {settings.network}.")
