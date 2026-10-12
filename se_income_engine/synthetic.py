"""Synthetic statement builder (Section 27.2: synthetic golden statements), used by the tests and the UI demo."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from se_income_engine.contracts.account import AccountInput, Transaction
from se_income_engine.contracts.enums import AccountType, Direction, LegalOwnerType, SourceType
from se_income_engine.pipeline.context import AnalysisRequest, BorrowerContext

HOLDER = "RAVI KUMAR"
_FIRST = ["AMIT", "SUNIL", "PRIYA", "NEHA", "RAHUL", "VIKAS", "POOJA", "ANIL", "DEEPAK", "KAVITA", "MANOJ", "SEEMA",
          "AJAY", "REKHA", "SANJAY", "GEETA", "ROHIT", "ANITA", "VIJAY", "SUMAN"]
_LAST = ["SHARMA", "VERMA", "GUPTA", "SINGH", "YADAV", "PATEL", "JAIN", "MISHRA", "TIWARI", "SAXENA"]
_BANKS = ["SBIN", "HDFC", "ICIC", "UTIB", "PUNB", "BARB", "KKBK", "YESB"]
_PSP = ["OKAXIS", "OKHDFCBANK", "YBL", "PAYTM", "IBL", "OKSBI"]


@dataclass
class _Row:
    booking_date: date
    direction: Direction
    amount: Decimal
    narration: str | None
    parser_fields: dict[str, str] = field(default_factory=dict)


class StatementBuilder:
    def __init__(self, account_id: str = "ACC1", masked_account: str = "XXXXXX1234", start: date = date(2025, 1, 1),
                 months: int = 12, opening_balance: Decimal = Decimal("200000"),
                 account_type: AccountType = AccountType.CURRENT, legal_owner_type: LegalOwnerType = LegalOwnerType.SOLE_PROP,
                 holder_name: str = HOLDER, seed: int = 7):
        self.account_id = account_id
        self.masked_account = masked_account
        self.start = start
        self.end = _add_months(start, months) - timedelta(days=1)
        self.opening = opening_balance
        self.account_type = account_type
        self.legal_owner_type = legal_owner_type
        self.holder_name = holder_name
        self.rng = random.Random(seed)
        self.rows: list[_Row] = []
        self._rrn = 400000000000 + seed * 1000003

    # --- primitive rows
    def rrn(self) -> str:
        self._rrn += 7919
        return str(self._rrn)[-12:]

    def credit(self, d: date, amount, narration: str | None, mode: str | None = None,
               payment_mode: str | None = None, **parser_fields) -> "StatementBuilder":
        """``mode`` / ``payment_mode`` fill the analyser's ``Mode`` and ``Payment Mode`` columns."""
        self.rows.append(_Row(d, Direction.CREDIT, Decimal(str(amount)), narration,
                              _source_fields(mode, payment_mode, parser_fields)))
        return self

    def debit(self, d: date, amount, narration: str | None, mode: str | None = None,
              payment_mode: str | None = None, **parser_fields) -> "StatementBuilder":
        self.rows.append(_Row(d, Direction.DEBIT, Decimal(str(amount)), narration,
                              _source_fields(mode, payment_mode, parser_fields)))
        return self

    def days(self):
        d = self.start
        while d <= self.end:
            yield d
            d += timedelta(days=1)

    # --- business behaviour
    def upi_receipt(self, d: date, amount, name: str | None = None) -> "StatementBuilder":
        name = name or self.customer_name()
        local = name.split()[0].lower() + str(int(hashlib.sha256(name.encode()).hexdigest(), 16) % 997)
        return self.credit(d, amount, f"UPI/{self.rrn()}/CR/{name}/{self.rng.choice(_BANKS)}/{local}@"
                                      f"{self.rng.choice(_PSP).lower()}", "UPI", f"Fund Transfer from {name}")

    def customer_name(self) -> str:
        return f"{self.rng.choice(_FIRST)} {self.rng.choice(_LAST)}"

    def typical_trading_business(self, daily_receipts=(8, 14), ticket_mu=6.4, supplier_share=0.62,
                                 rent=15000, salaries=(12000, 11000), owner_draw=25000) -> "StatementBuilder":
        """Kirana/trading archetype: many small UPI receipts, weekly supplier NEFTs, fixed monthly costs."""
        suppliers = ["SHARMA TRADERS", "BALAJI DISTRIBUTORS", "GANESH AGENCIES"]
        week_sales = Decimal("0")
        for d in self.days():
            for _ in range(self.rng.randint(*daily_receipts)):
                amt = Decimal(str(round(min(6000.0, self.rng.lognormvariate(ticket_mu, 0.6)), 0)))
                week_sales += amt
                self.upi_receipt(d, amt)
            if d.weekday() == 5:
                for i, s in enumerate(suppliers):
                    share = week_sales * Decimal(str(supplier_share)) * Decimal(("0.5", "0.3", "0.2")[i])
                    self.debit(d, share.quantize(Decimal("1")), f"NEFT/N{self.rrn()}/{s}/HDFC0001234", "NEFT",
                               f"Fund Transfer to {s}")
                week_sales = Decimal("0")
            if d.day == 3:
                self.debit(d, rent, f"IMPS/{self.rrn()}/RENT/MAHESH GUPTA", "IMPS", "Fund Transfer to MAHESH GUPTA")
            if d.day == 1:
                for i, sal in enumerate(salaries):
                    staff = f"STAFF {('RAJU', 'SHYAM')[i]} PAL"
                    self.debit(d, sal, f"NEFT/N{self.rrn()}/SALARY/{staff}", "NEFT", f"Fund Transfer to {staff}")
            if d.day == 10:
                self.debit(d, round(2500 + self.rng.random() * 1200), f"BBPS/MSEDCL ELECTRICITY/{self.rrn()}", "Other",
                           "Fund Transfer to MSEDCL ELECTRICITY")
            if d.day == 15:
                self.debit(d, owner_draw, f"UPI/{self.rrn()}/DR/{self.holder_name}/HDFC/ravi.kumar@okhdfcbank", "UPI",
                           f"Fund Transfer to {self.holder_name}")
            if d.day == 28 and d.month % 3 == 0:
                self.debit(d, 59, "SMS CHGS QTR", "Other", "Bank Charges")
                self.credit(d, 312, "SB INT PD", "Other", "Interest Received")
        return self

    def lagged_cycle_business(self, lag_weeks: int = 3, conversion: float = 1.4, base_purchase: float = 60000.0,
                              final_weeks: int = 3, final_purchase_factor: float = 1.0) -> "StatementBuilder":
        """Inventory trader whose weekly purchases convert into collections `lag_weeks` later (UT-10 / UT-11).
        The last `final_weeks` purchases are scaled by `final_purchase_factor` (surge > 1, suppression < 1)."""
        weeks = []
        d = self.start + timedelta(days=(7 - self.start.weekday()) % 7)
        while d + timedelta(days=6) <= self.end:
            weeks.append(d)
            d += timedelta(days=7)
        purchases = [base_purchase * (0.5 + self.rng.random()) for _ in weeks]
        for i in range(len(weeks) - final_weeks, len(weeks)):
            purchases[i] = base_purchase * final_purchase_factor
        for i, monday in enumerate(weeks):
            self.debit(monday, round(purchases[i]), f"NEFT/N{self.rrn()}/SHARMA TRADERS/HDFC0001234", "NEFT",
                       "Fund Transfer to SHARMA TRADERS")
            src = i - lag_weeks
            weekly_collections = conversion * (purchases[src] if src >= 0 else base_purchase)
            receipts = 40
            for k in range(receipts):
                self.upi_receipt(monday + timedelta(days=k % 6), round(weekly_collections / receipts))
            if monday.day <= 7:
                self.debit(monday, 15000, f"IMPS/{self.rrn()}/RENT/MAHESH GUPTA", "IMPS", "Fund Transfer to MAHESH GUPTA")
        return self

    # --- materialise
    def build(self) -> AccountInput:
        rows = sorted(enumerate(self.rows), key=lambda r: (r[1].booking_date, r[0]))
        bal = self.opening
        txns = []
        for seq, (_, r) in enumerate(rows):
            bal = bal + r.amount if r.direction == Direction.CREDIT else bal - r.amount
            key = f"{self.account_id}|{seq}|{r.booking_date}|{r.amount}|{r.narration}"
            txns.append(Transaction(
                transaction_id=hashlib.sha256(key.encode()).hexdigest()[:24],
                account_id=self.account_id,
                booking_date=r.booking_date,
                direction=r.direction,
                amount=r.amount,
                value_date=r.booking_date,
                sequence_no=seq,
                balance_after=bal,
                raw_narration=r.narration,
                parser_fields=dict(r.parser_fields),
            ))
        return AccountInput(
            account_id=self.account_id, customer_id="CUST1", account_type=self.account_type,
            legal_owner_type=self.legal_owner_type, currency="INR", statement_start=self.start,
            statement_end=self.end, source_type=SourceType.API, parser_version="synthetic_v1", transactions=txns,
            parser_metadata={"holder_name": self.holder_name, "masked_account": self.masked_account},
        )


def _source_fields(mode: str | None, payment_mode: str | None, extra: dict[str, str]) -> dict[str, str]:
    fields = dict(extra)
    if mode is not None:
        fields["Mode"] = mode
    if payment_mode is not None:
        fields["Payment Mode"] = payment_mode
    return fields


def _add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    return date(d.year + y, m + 1, 1)


def make_request(*accounts: AccountInput, legal: LegalOwnerType = LegalOwnerType.SOLE_PROP,
                 documents: dict | None = None, as_of: date | None = None) -> AnalysisRequest:
    as_of = as_of or max(a.statement_end for a in accounts)
    return AnalysisRequest(
        customer_id="CUST1", application_id="APP1", as_of_date=as_of, accounts=list(accounts),
        borrower_context=BorrowerContext(legal_owner_type=legal, application_date=as_of, documents=documents or {}),
        policy_id="SE_INCOME_POLICY_001",
    )


def business(seed: int = 7, months: int = 12, **kwargs) -> StatementBuilder:
    return StatementBuilder(seed=seed, months=months, **kwargs).typical_trading_business()
