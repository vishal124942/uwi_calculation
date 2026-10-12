"""Canonical account and transaction objects (Sections 3.1 and 3.2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from se_income_engine.contracts.enums import (
    AccountType,
    ChannelFamily,
    Direction,
    LegalOwnerType,
    SourceType,
)


@dataclass
class Transaction:
    transaction_id: str
    account_id: str
    booking_date: date
    direction: Direction
    amount: Decimal
    value_date: date | None = None
    sequence_no: int = 0
    balance_after: Decimal | None = None
    balance_before: Decimal | None = None
    raw_narration: str | None = None
    normalized_narration: str | None = None
    source_reference: str | None = None
    channel_family: ChannelFamily = ChannelFamily.UNKNOWN
    # Source payment rail ("UPI", "CASH-BANK BRANCH", ...) and Payment Mode category ("FUND TRANSFER",
    # "BANK CHARGES", ...), both upper-cased from parser_fields during canonicalisation.
    mode: str | None = None
    payment_mode: str | None = None
    parser_fields: dict[str, str] = field(default_factory=dict)
    source_page: int | None = None
    source_line: int | None = None
    parse_confidence: float = 1.0

    @property
    def signed_amount(self) -> Decimal:
        return self.amount if self.direction == Direction.CREDIT else -self.amount

    @property
    def is_credit(self) -> bool:
        return self.direction == Direction.CREDIT


@dataclass
class AccountInput:
    account_id: str
    customer_id: str
    account_type: AccountType
    legal_owner_type: LegalOwnerType
    currency: str
    statement_start: date
    statement_end: date
    source_type: SourceType
    parser_version: str
    transactions: list[Transaction]
    bank_code: str | None = None
    sanctioned_limit: Decimal | None = None
    drawing_power: Decimal | None = None
    # Extension: parser-level metadata (holder name, source record counts). Never used as a universal economic field.
    parser_metadata: dict[str, str] = field(default_factory=dict)
