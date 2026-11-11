"""Solana Pay transfer-request links.

    solana:<recipient>?amount=<decimal>&spl-token=<mint>&reference=<pubkey>&label=…&message=…&memo=…

A link only *describes* a payment; it goes through exactly the same path as a typed
request (grant check, simulation, firewall, audit). Supported: transfer requests with
an amount. Refused:

- transaction requests (``solana:https://…``): the merchant's server would hand us an
  arbitrary transaction to sign, which Sightline never does;
- links without an amount: the user has to say how much.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import parse_qs, unquote, urlsplit

from .amounts import AmountError, to_decimal
from .tokens import AddressError, parse_address

MAX_MEMO_BYTES = 256  # keeps the transaction small; Solana Pay doesn't set a limit
_AMOUNT = re.compile(r"^\d+(\.\d+)?$")  # spec: plain decimal, no sign, no exponent


class LinkError(ValueError):
    code = "invalid_payment_link"


@dataclass(frozen=True)
class PaymentLink:
    recipient: str
    amount: str
    token: str = "SOL"  # "SOL" or the spl-token mint
    references: tuple[str, ...] = field(default_factory=tuple)
    memo: str | None = None
    label: str | None = None
    message: str | None = None


def is_link(value) -> bool:
    return isinstance(value, str) and value.strip().lower().startswith("solana:")


def parse(link: str) -> PaymentLink:
    text = (link or "").strip()
    if not is_link(text):
        raise LinkError("not a Solana Pay link (it must start with 'solana:')")
    body = text[len("solana:"):]
    if body.lower().startswith(("http://", "https://", "http%3a", "https%3a")):
        raise LinkError("this is a Solana Pay *transaction request*: the merchant's server would send a "
                        "ready-made transaction to sign. Sightline only pays transfer requests it builds itself.")
    parts = urlsplit("x:" + body)
    recipient = unquote(parts.path)
    try:
        parse_address(recipient, "recipient")
    except AddressError as exc:
        raise LinkError(f"bad recipient in link: {exc}") from None

    query = parse_qs(parts.query, keep_blank_values=True, strict_parsing=False)
    for key, values in query.items():
        if key != "reference" and len(values) > 1:
            raise LinkError(f"link repeats '{key}'")

    raw_amount = (query.get("amount") or [""])[0]
    if not raw_amount:
        raise LinkError("link has no amount; ask the user how much to send")
    if not _AMOUNT.match(raw_amount):
        raise LinkError(f"bad amount in link: {raw_amount!r}")
    try:
        amount = str(to_decimal(raw_amount))
    except AmountError as exc:
        raise LinkError(f"bad amount in link: {exc}") from None

    token = "SOL"
    if "spl-token" in query:
        token = query["spl-token"][0]
        try:
            parse_address(token, "spl-token mint")
        except AddressError as exc:
            raise LinkError(f"bad spl-token in link: {exc}") from None

    references = tuple(query.get("reference", []))
    for ref in references:
        try:
            parse_address(ref, "reference")
        except AddressError as exc:
            raise LinkError(f"bad reference in link: {exc}") from None
    if len(set(references)) != len(references) or len(references) > 5:
        raise LinkError("link has duplicate or too many references (max 5)")

    memo = (query.get("memo") or [None])[0]
    if memo is not None and len(memo.encode()) > MAX_MEMO_BYTES:
        raise LinkError(f"memo is longer than {MAX_MEMO_BYTES} bytes")

    return PaymentLink(recipient=recipient, amount=amount, token=token, references=references,
                       memo=memo or None, label=(query.get("label") or [None])[0],
                       message=(query.get("message") or [None])[0])
