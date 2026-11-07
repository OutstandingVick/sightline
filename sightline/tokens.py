"""Known token mints per cluster and symbol/mint resolution."""

from __future__ import annotations

from dataclasses import dataclass

from solders.pubkey import Pubkey

WSOL_MINT = "So11111111111111111111111111111111111111112"

KNOWN_MINTS: dict[str, dict[str, str]] = {
    "devnet": {
        "USDC": "4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU",
        "EURC": "HzwqbKZw8HxMN6bF2yFZNrht3c2iXXzpKcFu7uBEDKtr",
        "WSOL": WSOL_MINT,
    },
    "mainnet": {
        "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "WSOL": WSOL_MINT,
    },
}


class AddressError(ValueError):
    pass


def parse_address(value: str, what: str = "address") -> Pubkey:
    """Validate a base58 Solana address."""
    if not isinstance(value, str) or not value.strip():
        raise AddressError(f"{what} is empty")
    try:
        return Pubkey.from_string(value.strip())
    except Exception:
        raise AddressError(f"invalid {what}: {value!r}") from None


def short(address: str) -> str:
    return f"{address[:4]}…{address[-4:]}"


def symbol_for(mint: str, network: str) -> str | None:
    for sym, m in KNOWN_MINTS.get(network, {}).items():
        if m == mint:
            return sym
    return None


@dataclass(frozen=True)
class TokenRef:
    """What the user asked to send: native SOL, or an SPL mint."""

    native: bool
    mint: Pubkey | None = None
    symbol: str | None = None


def resolve_token(token: str | None, network: str) -> TokenRef:
    """"SOL" → native; known symbol → its mint; otherwise must be a mint address."""
    raw = (token or "SOL").strip()
    if raw.upper() == "SOL":
        return TokenRef(native=True, symbol="SOL")
    mint = KNOWN_MINTS.get(network, {}).get(raw.upper())
    if mint:
        return TokenRef(native=False, mint=Pubkey.from_string(mint), symbol=raw.upper())
    try:
        pk = Pubkey.from_string(raw)
    except Exception:
        known = ", ".join(["SOL", *KNOWN_MINTS.get(network, {})])
        raise AddressError(f"unknown token {raw!r} on {network}; use one of {known} or a mint address") from None
    return TokenRef(native=False, mint=pk, symbol=symbol_for(str(pk), network))
