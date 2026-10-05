"""Section 3.4 - Channel-family normalisation (part of M1 Parser/normaliser)."""

from __future__ import annotations

import re

from se_income_engine.contracts.account import Transaction
from se_income_engine.contracts.enums import ChannelFamily

# Ordered: the first matching rule wins. Fee/interest markers precede payment rails because
# bank charge narrations frequently embed rail tokens.
_CHANNEL_RULES: list[tuple[ChannelFamily, re.Pattern]] = [
    (ChannelFamily.FEE_CHARGE, re.compile(
        r"\b(CHGS?|CHRGS?|CHARGES?|MIN[_ ]?BAL|AMC|SMS[_ ]?CHG|SMS|PENALTY|FEE|CGST|SGST|IGST|"
        r"CHARGES RECOVERY|GENERAL CHARGES)\b|_CHGS?_|MIN_BAL|QTR_MIN_BAL")),
    (ChannelFamily.INTEREST, re.compile(r"\b(INT\.?\s?PD|INT\.?\s?CR|SB\s?INT|INTEREST|INT\s?PAID|CREDIT INTEREST)\b")),
    (ChannelFamily.ACH_NACH, re.compile(r"\b(NACH|ACH|ECS|E-?MANDATE|EMANCH|UMRN)\b|UPIMAND|MANDATE")),
    (ChannelFamily.MERCHANT_SETTLEMENT, re.compile(
        r"\b(SETTLEMENT|SETL|STLMT|RAZORPAY|PAYU|CASHFREE|CCAVENUE|PINELABS|MSWIPE|BHARATPE\s?SETT|"
        r"PAYTM\s?SETT|EZETAP|INSTAMOJO)\b")),
    (ChannelFamily.ATM, re.compile(r"\b(ATM|ATW|NFS|CWDR|ATM WDL)\b")),
    (ChannelFamily.CASH, re.compile(
        r"\b(CASH\s?DEP|BY CASH|CASH DEPOSIT|CSH DEP|CASH WDL|CASH WITHDRAWAL|SELF CASH|BNA)\b|AEPS-[A-Z]*-?CW|AEPS.*CW")),
    (ChannelFamily.CHEQUE, re.compile(r"\b(CHQ|CHEQUE|CLG|CLEARING|INWARD CLG|OUTWARD CLG|CTS)\b")),
    (ChannelFamily.CMS, re.compile(r"\bCMS\b")),
    (ChannelFamily.RTGS, re.compile(r"\bRTGS\b")),
    (ChannelFamily.NEFT, re.compile(r"\b(NEFT|NEF)\b")),
    (ChannelFamily.IMPS, re.compile(r"\bIMPS|\bMMT\b|\bP2A\b|\bP2P\b")),
    (ChannelFamily.UPI, re.compile(r"\bUPI|MPAY/UPI|UPIAB|UPIAR|@[A-Z]{2,}")),
    (ChannelFamily.POS_CARD, re.compile(r"\b(POS|PCD|ECOM|CARD\s?TXN|VPS|VIN)\b")),
    (ChannelFamily.INTERNAL_BOOK, re.compile(r"\b(SWEEP|BOOK TRANSFER|TRF TO OWN|OWN A/?C|SELF TRANSFER|AUTO SWEEP)\b")),
]

# Hints from upstream parser fields (bank/vendor specific) used only when narration evidence is absent.
_PARSER_MODE_HINTS: dict[str, ChannelFamily] = {
    "UPI": ChannelFamily.UPI,
    "IMPS": ChannelFamily.IMPS,
    "NEFT": ChannelFamily.NEFT,
    "RTGS": ChannelFamily.RTGS,
    "CASH-BANK BRANCH": ChannelFamily.CASH,
    "CASH-CMS": ChannelFamily.CASH,
    "CHEQUE": ChannelFamily.CHEQUE,
    "NACH": ChannelFamily.ACH_NACH,
}


def normalize_channel(txn: Transaction) -> ChannelFamily:
    text = txn.normalized_narration or ""
    for family, pattern in _CHANNEL_RULES:
        if text and pattern.search(text):
            return family
    mode = (txn.parser_fields.get("Mode") or "").strip().upper()
    if mode in _PARSER_MODE_HINTS:
        return _PARSER_MODE_HINTS[mode]
    if text:
        return ChannelFamily.OTHER if re.search(r"\b(EFT|CRTR|TPD|TRF|TRANSFER)\b", text) else ChannelFamily.UNKNOWN
    return ChannelFamily.UNKNOWN
