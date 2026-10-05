"""Decimal money helpers. Money is never held in binary floating point (Section 3.3)."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")
ZERO = Decimal("0")


def to_money(value) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value.quantize(CENT, rounding=ROUND_HALF_UP)
    text = str(value).strip().replace(",", "")
    if text == "" or text.lower() in {"nan", "none", "null"}:
        return None
    try:
        return Decimal(text).quantize(CENT, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None


def weighted(amount: Decimal, probability: float) -> Decimal:
    """Probability-weighted amount, kept in Decimal."""
    return amount * Decimal(repr(round(probability, 8)))


def quantize(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def per_month(total: Decimal, months: float) -> Decimal:
    if months <= 0:
        return ZERO
    return quantize(total / Decimal(repr(months)))
