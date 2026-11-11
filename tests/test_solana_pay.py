"""Solana Pay transfer-request links: parsed strictly, transaction requests refused."""

import pytest
from solders.keypair import Keypair

from sightline.solana_pay import LinkError, is_link, parse

R = str(Keypair().pubkey())
MINT = "4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU"
REF = str(Keypair().pubkey())


def test_sol_link():
    p = parse(f"solana:{R}?amount=0.01&label=Coffee%20Shop&message=Thanks!&memo=order-42")
    assert (p.recipient, p.amount, p.token) == (R, "0.01", "SOL")
    assert (p.label, p.message, p.memo) == ("Coffee Shop", "Thanks!", "order-42")


def test_spl_link_with_references():
    p = parse(f"solana:{R}?amount=1.5&spl-token={MINT}&reference={REF}")
    assert p.token == MINT and p.references == (REF,) and p.amount == "1.5"


def test_is_link():
    assert is_link(f"  SOLANA:{R}?amount=1") and not is_link(R) and not is_link(1)


@pytest.mark.attack
def test_transaction_requests_are_refused():
    with pytest.raises(LinkError, match="transaction request"):
        parse("solana:https://merchant.example/api/pay")
    with pytest.raises(LinkError, match="transaction request"):
        parse("solana:https%3A%2F%2Fmerchant.example%2Fapi")


@pytest.mark.parametrize("link,why", [
    (f"solana:{R}", "no amount"),
    (f"solana:{R}?amount=", "no amount"),
    (f"solana:{R}?amount=-1", "bad amount"),
    (f"solana:{R}?amount=1e3", "bad amount"),
    (f"solana:{R}?amount=0", "bad amount"),
    ("solana:notanaddress?amount=1", "bad recipient"),
    (f"solana:{R}?amount=1&spl-token=nope", "bad spl-token"),
    (f"solana:{R}?amount=1&reference=nope", "bad reference"),
    (f"solana:{R}?amount=1&amount=2", "repeats 'amount'"),
    (f"solana:{R}?amount=1&reference={REF}&reference={REF}", "duplicate"),
    (f"solana:{R}?amount=1&memo={'x' * 300}", "memo is longer"),
    (f"bitcoin:{R}?amount=1", "not a Solana Pay link"),
])
def test_bad_links(link, why):
    with pytest.raises(LinkError, match=why):
        parse(link)
