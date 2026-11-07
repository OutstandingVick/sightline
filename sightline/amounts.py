"""Exact amount conversion. Decimal only: floats never touch base units."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

LAMPORTS_PER_SOL = 10**9
SOL_DECIMALS = 9


class AmountError(ValueError):
    pass


def to_decimal(amount) -> Decimal:
    if isinstance(amount, bool):
        raise AmountError("amount must be a number")
    try:
        # str() first so 0.1 (float) becomes Decimal("0.1"), not 0.1000000000000000055...
        value = Decimal(str(amount).strip())
    except (InvalidOperation, ValueError):
        raise AmountError(f"not a number: {amount!r}") from None
    if not value.is_finite():
        raise AmountError("amount must be finite")
    if value <= 0:
        raise AmountError("amount must be greater than zero")
    return value


def to_base_units(amount, decimals: int) -> int:
    """Convert a UI amount to integer base units; reject sub-unit precision."""
    value = to_decimal(amount)
    scaled = value.scaleb(decimals)
    if scaled != scaled.to_integral_value():
        raise AmountError(f"too many decimal places (max {decimals})")
    return int(scaled)


def from_base_units(units: int, decimals: int) -> Decimal:
    return Decimal(units).scaleb(-decimals)


def format_amount(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return text
