"""Section 5.2 - Narration parsing and structured identifier extraction."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from se_income_engine.contracts.account import Transaction

_VPA = re.compile(r"([A-Z0-9.\-_]{2,})@([A-Z]{2,})")
_IFSC = re.compile(r"\b([A-Z]{4}0[A-Z0-9]{6})\b")
# In UPI/IMPS narrations the counterparty bank is the last 4-letter segment followed by further text
# (".../NAME/HDFC/XXX", ".../NAME/SBIN/vpa@psp"); earlier 4-letter segments are bank transaction-type codes.
_BANK_SEGMENT = re.compile(r"/([A-Z]{4})(?=/)")
_NON_BANK_CODES = {"TRTR", "TRRR", "CRTR", "MPAY", "NEFT", "IMPS", "RTGS", "NACH", "CASH", "SELF"}
_RRN = re.compile(r"(?<!\d)(\d{12})(?!\d)")
_LONG_ACCOUNT = re.compile(r"(?<!\d)(\d{9,18})(?!\d)")
_MASKED_ACCOUNT = re.compile(r"X{2,}(\d{3,6})")
_MANDATE = re.compile(r"(?:UMRN|MANDATE|UPIMAND\w*|NACH|ECS)[\s:/\-]*([A-Z0-9]{6,})")
_CHEQUE = re.compile(r"(?:CHQ|CHEQUE|CLG|CTS)\D{0,5}(\d{6})")
_MERCHANT = re.compile(r"\b(?:MID|MERCHANT ID)[\s:]*([A-Z0-9]{5,})")
_TERMINAL = re.compile(r"\b(?:TID|TERMINAL)[\s:]*([A-Z0-9]{5,})")
# Redacted/masked tokens (XXXX, ****) carry no identity and must never link entities.
_MASK_TOKEN = re.compile(r"^[X*#]+\d{0,4}$")

_STOPWORDS = {
    "UPI", "MPAY", "TRTR", "CR", "DR", "NEFT", "IMPS", "RTGS", "XX", "XXX", "UPIAB", "UPIAR", "TRANSFER", "FUND",
    "TO", "FROM", "BY", "THE", "MR", "MRS", "MS", "SHRI", "SMT", "PAYMENT", "TRF", "BANK", "ACCOUNT", "LTD",
    "LIMITED", "PVT", "AND", "OF", "ONUS", "TPD", "CD", "IN", "OUT", "SELF", "NA", "REF", "RRN", "PAY",
    "TRTR", "TRRR", "CRTR", "IMPSI", "IMPSAB", "EFT",
}


@dataclass
class TransactionIdentifiers:
    vpa_local: str | None = None
    vpa_psp: str | None = None
    ifsc: str | None = None
    bank_code: str | None = None
    utr: str | None = None
    account_fragment: str | None = None
    merchant_id: str | None = None
    terminal_id: str | None = None
    mandate_id: str | None = None
    cheque_no: str | None = None
    name_tokens: tuple[str, ...] = field(default_factory=tuple)
    reference_signature: str | None = None
    own_account_marker: bool = False
    holder_name_match: float = 0.0


def hash_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def reference_signature(text: str | None) -> str | None:
    """Token-family signature: first structural segments with digits masked (Section 5.2 UTR/reference family)."""
    if not text:
        return None
    segments = re.split(r"[/:\-]", text)[:3]
    shaped = [re.sub(r"\d", "9", s.strip())[:16] for s in segments]
    return hash_value("/".join(shaped))


def _name_tokens(txn: Transaction, bank_codes: set[str]) -> tuple[str, ...]:
    candidate = (txn.parser_fields.get("Entity Name") or "").upper()
    if not candidate and txn.normalized_narration:
        segments = re.split(r"[/:\-]", txn.normalized_narration)
        candidate = " ".join(s for s in segments if re.search(r"[A-Z]{3,}", s) and not re.search(r"\d{4,}", s))
    tokens = [t for t in re.findall(r"[A-Z]{2,}", candidate)
              if t not in _STOPWORDS and t not in bank_codes and not _MASK_TOKEN.match(t)]
    return tuple(dict.fromkeys(tokens))


def extract_identifiers(txn: Transaction, holder_name: str | None = None,
                        holder_account_suffix: str | None = None) -> TransactionIdentifiers:
    text = txn.normalized_narration or ""
    ids = TransactionIdentifiers()

    if (m := _VPA.search(text)) and not _MASK_TOKEN.match(m.group(1)):
        ids.vpa_local, ids.vpa_psp = m.group(1), m.group(2)
    if m := _IFSC.search(text):
        ids.ifsc = m.group(1)
        ids.bank_code = m.group(1)[:4]
    else:
        segments = [s for s in _BANK_SEGMENT.findall(text) if s not in _NON_BANK_CODES and not _MASK_TOKEN.match(s)]
        ids.bank_code = segments[-1] if segments else None
    if m := _RRN.search(text):
        ids.utr = m.group(1)
    for m in _LONG_ACCOUNT.finditer(text):
        if m.group(1) != ids.utr:
            ids.account_fragment = m.group(1)
    if not ids.account_fragment and (m := _MASKED_ACCOUNT.search(text)):
        ids.account_fragment = m.group(1)
    if m := _MANDATE.search(text):
        ids.mandate_id = m.group(1)
    if m := _CHEQUE.search(text):
        ids.cheque_no = m.group(1)
    if m := _MERCHANT.search(text):
        ids.merchant_id = m.group(1)
    if m := _TERMINAL.search(text):
        ids.terminal_id = m.group(1)

    bank_codes = {ids.bank_code} if ids.bank_code else set()
    ids.name_tokens = _name_tokens(txn, bank_codes)
    ids.reference_signature = reference_signature(text)

    if holder_account_suffix and ids.account_fragment and ids.account_fragment.endswith(holder_account_suffix):
        ids.own_account_marker = True
    if holder_name and ids.name_tokens:
        holder_tokens = {t for t in re.findall(r"[A-Z]{2,}", holder_name.upper()) if t not in _STOPWORDS}
        overlap = holder_tokens.intersection(ids.name_tokens)
        if holder_tokens:
            ids.holder_name_match = len(overlap) / min(len(holder_tokens), max(1, len(ids.name_tokens)))
    if re.search(r"\b(SELF|OWN A/?C|OWN ACCOUNT)\b", text):
        ids.own_account_marker = True
    return ids
