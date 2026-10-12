"""Section 25.1 request contract (pydantic) and its mapping onto the internal dataclass contracts."""

from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from se_income_engine.contracts.account import AccountInput, Transaction
from se_income_engine.contracts.enums import AccountType, Direction, LegalOwnerType, SourceType
from se_income_engine.pipeline.context import AnalysisRequest, BorrowerContext


class TransactionIn(BaseModel):
    """Section 3.2 canonical transaction input."""

    transaction_id: str | None = None
    booking_date: date
    value_date: date | None = None
    sequence_no: int = 0
    direction: Direction
    amount: Decimal = Field(gt=0)
    balance_after: Decimal | None = None
    raw_narration: str | None = None
    source_reference: str | None = None
    parser_fields: dict[str, str] = Field(
        default_factory=dict,
        description="Source columns as exported; 'Mode' and 'Payment Mode' decide the channel family (Section 3.4)")
    source_page: int | None = None
    source_line: int | None = None
    parse_confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class AccountIn(BaseModel):
    """Section 3.1 account input."""

    account_id: str
    customer_id: str | None = None
    account_type: AccountType = AccountType.OTHER
    legal_owner_type: LegalOwnerType = LegalOwnerType.UNKNOWN
    currency: str = "INR"
    statement_start: date
    statement_end: date
    source_type: SourceType = SourceType.API
    parser_version: str = "api_v1"
    bank_code: str | None = None
    sanctioned_limit: Decimal | None = None
    drawing_power: Decimal | None = None
    holder_name: str | None = None
    masked_account: str | None = None
    transactions: list[TransactionIn]


class BorrowerContextIn(BaseModel):
    legal_owner_type: LegalOwnerType = LegalOwnerType.UNKNOWN
    declared_business_type: str | None = None
    application_date: date | None = None
    documents: dict = Field(default_factory=dict)


class AnalyseRequestIn(BaseModel):
    customer_id: str
    application_id: str
    as_of_date: date
    accounts: list[AccountIn] = Field(min_length=1)
    borrower_context: BorrowerContextIn = Field(default_factory=BorrowerContextIn)
    policy_id: str | None = "SE_INCOME_POLICY_001"


def _txn_id(account_id: str, t: TransactionIn, index: int) -> str:
    key = f"{account_id}|{t.booking_date}|{t.sequence_no}|{t.direction.value}|{t.amount}|{t.raw_narration}|{index}"
    return hashlib.sha256(key.encode()).hexdigest()[:24]


def to_analysis_request(body: AnalyseRequestIn) -> AnalysisRequest:
    accounts = []
    for a in body.accounts:
        txns = [
            Transaction(
                transaction_id=t.transaction_id or _txn_id(a.account_id, t, i),
                account_id=a.account_id,
                booking_date=t.booking_date,
                value_date=t.value_date,
                sequence_no=t.sequence_no or i,
                direction=t.direction,
                amount=t.amount,
                balance_after=t.balance_after,
                raw_narration=t.raw_narration,
                source_reference=t.source_reference,
                parser_fields=dict(t.parser_fields),
                source_page=t.source_page,
                source_line=t.source_line,
                parse_confidence=t.parse_confidence,
            )
            for i, t in enumerate(a.transactions)
        ]
        metadata = {k: v for k, v in (("holder_name", a.holder_name), ("masked_account", a.masked_account)) if v}
        accounts.append(AccountInput(
            account_id=a.account_id,
            customer_id=a.customer_id or body.customer_id,
            account_type=a.account_type,
            legal_owner_type=a.legal_owner_type,
            currency=a.currency,
            statement_start=a.statement_start,
            statement_end=a.statement_end,
            source_type=a.source_type,
            parser_version=a.parser_version,
            transactions=txns,
            bank_code=a.bank_code,
            sanctioned_limit=a.sanctioned_limit,
            drawing_power=a.drawing_power,
            parser_metadata=metadata,
        ))
    bc = body.borrower_context
    return AnalysisRequest(
        customer_id=body.customer_id,
        application_id=body.application_id,
        as_of_date=body.as_of_date,
        accounts=accounts,
        borrower_context=BorrowerContext(bc.legal_owner_type, bc.declared_business_type,
                                         bc.application_date or body.as_of_date, dict(bc.documents)),
        policy_id=body.policy_id,
    )
