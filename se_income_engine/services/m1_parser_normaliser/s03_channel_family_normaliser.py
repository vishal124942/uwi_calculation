"""Section 3.4 - Channel-family normalisation (part of M1 Parser/normaliser).

The channel family comes from the statement's own columns, never from narration text:

1. ``Mode`` is the payment rail the source reports (UPI, IMPS, NEFT, Cash-Bank Branch, ...) and decides the family.
2. Only when ``Mode`` names no rail (``Other`` or blank) does the ``Payment Mode`` category decide it, e.g. a
   ``Bank Charges`` row is FEE_CHARGE and an ``Interest Received`` row is INTEREST.

``Payment Mode`` is free text that often embeds the counterparty ("Fund Transfer to MADAN NARAYAN");
``payment_mode_category`` keeps only the category ("Fund Transfer").
"""

from __future__ import annotations

import re

from se_income_engine.contracts.account import Transaction
from se_income_engine.contracts.enums import ChannelFamily

# Analyser ``Mode`` values. UPI, IMPS, NEFT, Cash-Bank Branch, Cash-CMS and Other occur in the sample statements;
# RTGS, Cheque and NACH are the analyser's other rail values.
MODE_CHANNELS: dict[str, ChannelFamily] = {
    "UPI": ChannelFamily.UPI,
    "IMPS": ChannelFamily.IMPS,
    "NEFT": ChannelFamily.NEFT,
    "RTGS": ChannelFamily.RTGS,
    "CASH-BANK BRANCH": ChannelFamily.CASH,
    "CASH-CMS": ChannelFamily.CASH,
    "CHEQUE": ChannelFamily.CHEQUE,
    "NACH": ChannelFamily.ACH_NACH,
}

# ``Payment Mode`` categories that identify the channel of a row whose ``Mode`` names no rail. Categories that
# describe a purpose rather than a rail (Telephone, EMI, Gambling, ...) are left to the role model.
PAYMENT_MODE_CHANNELS: dict[str, ChannelFamily] = {
    "BANK CHARGES": ChannelFamily.FEE_CHARGE,
    "MINIMUM BALANCE CHARGES": ChannelFamily.FEE_CHARGE,
    # GST the bank levies on its own charges; a tax paid over UPI/NEFT keeps that rail.
    "STATUTORY PAYMENT-TAX": ChannelFamily.FEE_CHARGE,
    "INTEREST RECEIVED": ChannelFamily.INTEREST,
    "CASH DEPOSIT": ChannelFamily.CASH,
    "CASH WITHDRAWAL": ChannelFamily.CASH,
}

_FUND_TRANSFER = re.compile(r"^FUND TRANSFER\b")
_SPACES = re.compile(r"\s+")


def _clean(value: str | None) -> str:
    return _SPACES.sub(" ", value or "").strip().upper()


def payment_mode_category(payment_mode: str | None) -> str | None:
    """``"Fund Transfer to MADAN NARAYAN"`` / ``"Fund Transfer in "`` -> ``"FUND TRANSFER"``; other categories as-is."""
    text = _clean(payment_mode)
    if not text:
        return None
    return "FUND TRANSFER" if _FUND_TRANSFER.match(text) else text


def source_mode(txn: Transaction) -> str | None:
    return _clean(txn.parser_fields.get("Mode")) or None


def normalize_channel(txn: Transaction) -> ChannelFamily:
    mode = source_mode(txn)
    if mode in MODE_CHANNELS:
        return MODE_CHANNELS[mode]
    category = payment_mode_category(txn.parser_fields.get("Payment Mode"))
    if category in PAYMENT_MODE_CHANNELS:
        return PAYMENT_MODE_CHANNELS[category]
    return ChannelFamily.OTHER if mode == "OTHER" else ChannelFamily.UNKNOWN
