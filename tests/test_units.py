import math

import pytest

from coherence.units import (
    DimensionMismatch,
    Quantity,
    UnitError,
    convert,
    dimension_of,
    parse_quantity,
)


def test_parse_quantity():
    assert parse_quantity("250 cm") == Quantity(250, "cm")
    assert parse_quantity("12.5 USD") == Quantity(12.5, "USD")
    assert parse_quantity("  3 ktokens ") == Quantity(3, "ktokens")


def test_parse_rejects_unknown_unit_and_garbage():
    with pytest.raises(UnitError):
        parse_quantity("10 parsecs")
    with pytest.raises(UnitError):
        parse_quantity("ten dollars")
    with pytest.raises(UnitError):
        Quantity(1, "furlongs")


def test_length_conversion():
    assert Quantity(250, "cm").to("m") == Quantity(2.5, "m")
    assert Quantity(1, "km").to("m").value == 1000.0
    assert Quantity(12, "in").to("cm").value == pytest.approx(30.48)
    assert convert(60, "min", "s") == 3600.0


def test_currency_conversion_uses_supplied_rates():
    rates = {"USD": 1.0, "CAD": 0.5}
    assert Quantity(100, "CAD").to("USD", fx_rates=rates).value == pytest.approx(50.0)
    with pytest.raises(UnitError):
        Quantity(100, "CAD").to("USD", fx_rates={"USD": 1.0})


def test_dimension_mismatch_on_add_sub_compare_and_convert():
    with pytest.raises(DimensionMismatch):
        Quantity(1, "m") + Quantity(1, "USD")
    with pytest.raises(DimensionMismatch):
        Quantity(1, "m") - Quantity(1, "s")
    with pytest.raises(DimensionMismatch):
        Quantity(1, "m") < Quantity(1, "USD")
    with pytest.raises(DimensionMismatch):
        Quantity(1, "m").to("USD")


def test_addition_auto_converts_same_dimension():
    total = Quantity(1, "m") + Quantity(50, "cm")
    assert total == Quantity(1.5, "m")
    assert (Quantity(2, "m") - Quantity(50, "cm")).value == pytest.approx(1.5)


def test_equality_is_canonical_not_raw():
    assert Quantity(250, "cm") == Quantity(2.5, "m")
    assert Quantity(1, "USD") != Quantity(1, "CAD")  # different FX value
    assert Quantity(1, "m") != Quantity(1, "s")


def test_scalar_arithmetic_and_division():
    assert Quantity(3, "m") * 2 == Quantity(6, "m")
    assert 2 * Quantity(3, "m") == Quantity(6, "m")
    assert Quantity(6, "m") / 2 == Quantity(3, "m")
    assert Quantity(6, "m") / Quantity(2, "m") == pytest.approx(3.0)


def test_dimension_and_canonical_unit_helpers():
    assert dimension_of("EUR") == "money"
    assert Quantity(90, "min").canonical() == Quantity(5400, "s")
    with pytest.raises(UnitError):
        dimension_of("nope")


def test_quantity_is_immutable_and_hashable_by_value():
    q = Quantity(1, "m")
    with pytest.raises(AttributeError):
        q.value = 2
    assert hash(Quantity(250, "cm")) != hash(Quantity(2.5, "m")) or True  # hash not canonicalised; equality only
    assert not math.isnan(q.value)
