"""Section 3.3 - Transaction canonicalisation rules (part of M1 Parser/normaliser)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import replace
from decimal import Decimal

from se_income_engine.contracts.account import AccountInput, Transaction
from se_income_engine.services.m1_parser_normaliser.s03_channel_family_normaliser import (
    normalize_channel,
    payment_mode_category,
    source_mode,
)

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_REPEATED_SEPARATORS = re.compile(r"([/\-_|:,.])\1+")
_WHITESPACE = re.compile(r"\s+")


def normalise_narration(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = unicodedata.normalize("NFKC", raw)
    text = _CONTROL_CHARS.sub(" ", text)
    text = _REPEATED_SEPARATORS.sub(r"\1", text)
    text = _WHITESPACE.sub(" ", text).strip().upper()
    return text or None


def _ordering_key(txn: Transaction):
    return (
        txn.booking_date,
        txn.value_date or txn.booking_date,
        txn.source_page if txn.source_page is not None else 0,
        txn.source_line if txn.source_line is not None else 0,
        txn.sequence_no,
        txn.transaction_id,
    )


def _chain_breaks(txns: list[Transaction], opening: Decimal | None, tol: Decimal) -> int:
    breaks = 0
    prev = opening
    for t in txns:
        if t.balance_after is None:
            return 0
        if prev is not None and abs(prev + t.signed_amount - t.balance_after) > tol:
            breaks += 1
        prev = t.balance_after
    return breaks


def resolve_intraday_order(txns: list[Transaction], tol: Decimal = Decimal("0.05")) -> list[Transaction]:
    """Re-order same-day transactions only when the balance chain proves a different order.

    The reordering is accepted only if it removes every break for that day; otherwise source order is kept.
    """
    if not txns or any(t.balance_after is None for t in txns):
        return txns
    by_day: dict = {}
    for t in txns:
        by_day.setdefault(t.booking_date, []).append(t)
    result: list[Transaction] = []
    prev_balance: Decimal | None = None
    for day in sorted(by_day):
        day_txns = by_day[day]
        if prev_balance is not None and _chain_breaks(day_txns, prev_balance, tol):
            remaining = list(day_txns)
            chained: list[Transaction] = []
            current = prev_balance
            while remaining:
                nxt = next((t for t in remaining if abs(current + t.signed_amount - t.balance_after) <= tol), None)
                if nxt is None:
                    break
                chained.append(nxt)
                remaining.remove(nxt)
                current = nxt.balance_after
            if not remaining:
                day_txns = chained
        result.extend(day_txns)
        prev_balance = day_txns[-1].balance_after
    return result


def derive_balance_before(txns: list[Transaction]) -> None:
    prev: Decimal | None = None
    for t in txns:
        if prev is not None:
            t.balance_before = prev
        elif t.balance_after is not None:
            t.balance_before = t.balance_after - t.signed_amount
        prev = t.balance_after


def canonicalize_account(account: AccountInput) -> AccountInput:
    txns: list[Transaction] = []
    for t in account.transactions:
        c = replace(t, parser_fields=dict(t.parser_fields))
        c.amount = abs(c.amount)
        c.normalized_narration = normalise_narration(c.raw_narration)
        c.mode = source_mode(c)
        c.payment_mode = payment_mode_category(c.parser_fields.get("Payment Mode"))
        c.channel_family = normalize_channel(c)
        txns.append(c)
    txns.sort(key=_ordering_key)
    txns = resolve_intraday_order(txns)
    for i, t in enumerate(txns):
        t.sequence_no = i
    derive_balance_before(txns)
    return replace(account, transactions=txns, parser_metadata=dict(account.parser_metadata))


def canonicalize_all(accounts: list[AccountInput]) -> list[AccountInput]:
    return [canonicalize_account(a) for a in accounts]
