import pytest

from sightline.tokens import KNOWN_MINTS, AddressError, parse_address, resolve_token

ADDR = "535pnQVzoGKSkvTpwEm8WaAHZeRRkUvwi2HCw8M9CyBg"


def test_parse_valid_address():
    assert str(parse_address(ADDR)) == ADDR


@pytest.mark.parametrize("bad", ["", "   ", "not-an-address", ADDR[:-3], "0" * 44, None])
def test_parse_invalid_address(bad):
    with pytest.raises(AddressError):
        parse_address(bad)


def test_resolve_sol_default():
    assert resolve_token(None, "devnet").native
    assert resolve_token("sol", "devnet").native


def test_resolve_known_symbol_case_insensitive():
    ref = resolve_token("usdc", "devnet")
    assert str(ref.mint) == KNOWN_MINTS["devnet"]["USDC"] and ref.symbol == "USDC"


def test_symbol_is_per_network():
    assert resolve_token("USDC", "mainnet").mint != resolve_token("USDC", "devnet").mint


def test_resolve_mint_address_labels_known():
    ref = resolve_token(KNOWN_MINTS["devnet"]["USDC"], "devnet")
    assert ref.symbol == "USDC"


def test_resolve_unknown_mint_address():
    ref = resolve_token(ADDR, "devnet")
    assert not ref.native and ref.symbol is None


def test_resolve_unknown_symbol():
    with pytest.raises(AddressError, match="unknown token"):
        resolve_token("DOGE", "devnet")
