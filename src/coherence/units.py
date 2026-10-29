"""Typed quantities with explicit dimensions and unit conversion.

The harness never adds metres to dollars, and never compares a value in
centimetres with a value in metres without converting first. Currency
conversion uses rates supplied by the caller (see ``config/default.yaml``);
the built-in defaults are fixed illustrative rates and must be replaced
with live rates before any real money is involved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "UnitError",
    "DimensionMismatch",
    "Quantity",
    "parse_quantity",
    "convert",
    "DEFAULT_FX_RATES",
    "dimension_of",
    "canonical_unit",
]

# unit -> (dimension, factor to canonical unit of that dimension)
_UNITS = {
    # money: canonical USD
    "USD": ("money", 1.0),
    "CAD": ("money", 0.73),
    "EUR": ("money", 1.08),
    "GBP": ("money", 1.27),
    # length: canonical m
    "m": ("length", 1.0),
    "cm": ("length", 0.01),
    "mm": ("length", 0.001),
    "km": ("length", 1000.0),
    "ft": ("length", 0.3048),
    "in": ("length", 0.0254),
    # time: canonical s
    "s": ("time", 1.0),
    "sec": ("time", 1.0),
    "min": ("time", 60.0),
    "h": ("time", 3600.0),
    "day": ("time", 86400.0),
    # count: canonical items
    "items": ("count", 1.0),
    "calls": ("count", 1.0),
    # tokens: canonical tokens
    "tokens": ("tokens", 1.0),
    "ktokens": ("tokens", 1000.0),
    "mtokens": ("tokens", 1_000_000.0),
}

_CANONICAL = {
    "money": "USD",
    "length": "m",
    "time": "s",
    "count": "items",
    "tokens": "tokens",
}

# Fixed illustrative FX rates to USD, used only when no rates are supplied.
# They are not live market rates.
DEFAULT_FX_RATES = {"USD": 1.0, "CAD": 0.73, "EUR": 1.08, "GBP": 1.27}


class UnitError(ValueError):
    """Raised for unknown units and malformed quantity strings."""


class DimensionMismatch(ValueError):
    """Raised when two quantities of different dimensions are combined."""


def dimension_of(unit: str) -> str:
    try:
        return _UNITS[unit][0]
    except KeyError:
        raise UnitError(f"unknown unit: {unit!r}") from None


def canonical_unit(dimension: str) -> str:
    try:
        return _CANONICAL[dimension]
    except KeyError:
        raise UnitError(f"unknown dimension: {dimension!r}") from None


def _factor(unit: str, fx_rates=None) -> float:
    dimension, factor = _UNITS[unit]
    if dimension == "money" and fx_rates is not None:
        try:
            return float(fx_rates[unit])
        except KeyError:
            raise UnitError(f"no FX rate for currency: {unit!r}") from None
    return factor


@dataclass(frozen=True)
class Quantity:
    """A numeric value tagged with a unit. Arithmetic is dimension-checked."""

    value: float
    unit: str

    def __post_init__(self):
        dimension_of(self.unit)  # validates the unit eagerly

    @property
    def dimension(self) -> str:
        return dimension_of(self.unit)

    def to(self, unit: str, fx_rates=None) -> "Quantity":
        """Convert to another unit of the same dimension."""
        if dimension_of(unit) != self.dimension:
            raise DimensionMismatch(
                f"cannot convert {self.unit} ({self.dimension}) to {unit} "
                f"({dimension_of(unit)})"
            )
        canonical = self.value * _factor(self.unit, fx_rates)
        return Quantity(canonical / _factor(unit, fx_rates), unit)

    def canonical(self, fx_rates=None) -> "Quantity":
        return self.to(_CANONICAL[self.dimension], fx_rates)

    def _coerce(self, other, fx_rates=None):
        if isinstance(other, Quantity):
            return other.to(self.unit, fx_rates).value
        if isinstance(other, (int, float)):
            return float(other)
        return NotImplemented

    def __add__(self, other):
        if isinstance(other, Quantity) and other.dimension != self.dimension:
            raise DimensionMismatch(f"cannot add {self.unit} and {other.unit}")
        coerced = self._coerce(other)
        if coerced is NotImplemented:
            return NotImplemented
        return Quantity(self.value + coerced, self.unit)

    def __sub__(self, other):
        if isinstance(other, Quantity) and other.dimension != self.dimension:
            raise DimensionMismatch(f"cannot subtract {other.unit} from {self.unit}")
        coerced = self._coerce(other)
        if coerced is NotImplemented:
            return NotImplemented
        return Quantity(self.value - coerced, self.unit)

    def __mul__(self, scalar):
        if isinstance(scalar, (int, float)):
            return Quantity(self.value * scalar, self.unit)
        return NotImplemented

    def __rmul__(self, scalar):
        return self.__mul__(scalar)

    def __truediv__(self, other):
        if isinstance(other, Quantity):
            if other.dimension != self.dimension:
                raise DimensionMismatch("division of unlike dimensions")
            return self.value / other.to(self.unit).value
        if isinstance(other, (int, float)):
            return Quantity(self.value / other, self.unit)
        return NotImplemented

    def __eq__(self, other):
        if not isinstance(other, Quantity):
            return NotImplemented
        if other.dimension != self.dimension:
            return False
        return abs(self.canonical().value - other.canonical().value) < 1e-9

    def __lt__(self, other):
        if not isinstance(other, Quantity) or other.dimension != self.dimension:
            raise DimensionMismatch("cannot compare quantities of different dimensions")
        return self.canonical().value < other.canonical().value

    def __le__(self, other):
        return self < other or self == other

    def __gt__(self, other):
        return not self <= other

    def __ge__(self, other):
        return not self < other

    def __repr__(self):
        return f"Quantity({self.value!r}, {self.unit!r})"


_QUANTITY_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*([A-Za-z]+)\s*$")


def parse_quantity(text: str) -> Quantity:
    """Parse strings like ``"250 cm"`` or ``"12.5 USD"``."""
    match = _QUANTITY_RE.match(text)
    if not match:
        raise UnitError(f"cannot parse quantity: {text!r}")
    value, unit = float(match.group(1)), match.group(2)
    if unit not in _UNITS:
        raise UnitError(f"unknown unit: {unit!r}")
    return Quantity(value, unit)


def convert(value: float, from_unit: str, to_unit: str, fx_rates=None) -> float:
    """Convert a bare numeric value between two units of one dimension."""
    return Quantity(value, from_unit).to(to_unit, fx_rates).value
