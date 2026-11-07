from decimal import Decimal

import pytest

from sightline.amounts import AmountError, from_base_units, to_base_units


@pytest.mark.parametrize("amount,decimals,expected", [
    (0.1, 9, 100_000_000),
    ("0.000000001", 9, 1),
    (1, 6, 1_000_000),
    (0.3, 6, 300_000),  # float 0.3 is 0.299999...; str() path keeps it exact
    ("1.10", 2, 110),
    (123456789.123456789, 9, 123456789123456789),
])
def test_to_base_units_exact(amount, decimals, expected):
    assert to_base_units(amount, decimals) == expected


@pytest.mark.parametrize("bad", [0, -1, "abc", "nan", "inf", True, None])
def test_rejects_bad_amounts(bad):
    with pytest.raises(AmountError):
        to_base_units(bad, 9)


def test_rejects_sub_unit_precision():
    with pytest.raises(AmountError, match="decimal places"):
        to_base_units("0.0000001", 6)


def test_from_base_units():
    assert from_base_units(1_500_000, 6) == Decimal("1.5")
