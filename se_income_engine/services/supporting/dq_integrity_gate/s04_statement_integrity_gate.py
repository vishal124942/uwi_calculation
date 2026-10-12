"""Section 4 - Data Quality and Statement Integrity Gate."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from se_income_engine.common.money import ZERO
from se_income_engine.common.stats import DAYS_PER_MONTH, safe_div
from se_income_engine.config.parameters import DataQualityParameters
from se_income_engine.contracts.account import AccountInput
from se_income_engine.contracts.enums import AnalysisStatus


@dataclass
class AccountDataQuality:
    account_id: str
    metrics: dict[str, float | str | None]
    reconciliation_errors: dict[str, Decimal]
    break_transaction_ids: list[str]
    hard_stop_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class DataQualityReport:
    accounts: dict[str, AccountDataQuality]
    hard_stop: bool
    status: AnalysisStatus | None
    hard_stop_reasons: list[str]
    warnings: list[str]

    def metric(self, account_id: str, key: str):
        return self.accounts[account_id].metrics.get(key)


def reconcile_statement_arithmetic(account: AccountInput, tol: Decimal) -> tuple[dict[str, Decimal], list[str], int]:
    """Section 4.1: expected_balance_after[k] = balance_after[k-1] + credit[k] - debit[k]."""
    errors: dict[str, Decimal] = {}
    breaks: list[str] = []
    eligible = 0
    prev = None
    for t in account.transactions:
        if t.balance_after is None:
            prev = None
            continue
        if prev is not None:
            eligible += 1
            expected = prev + t.signed_amount
            err = abs(t.balance_after - expected)
            errors[t.transaction_id] = err
            if err > tol:
                breaks.append(t.transaction_id)
        prev = t.balance_after
    return errors, breaks, eligible


def _source_reliability(account: AccountInput, p: DataQualityParameters) -> float:
    key = account.source_type.value
    if key == "PDF" and "ocr" in account.parser_version.lower():
        key = "PDF_OCR"
    return p.source_reliability.get(key, 0.5)


def assess_account(account: AccountInput, p: DataQualityParameters) -> AccountDataQuality:
    txns = account.transactions
    n = len(txns)
    errors, breaks, eligible = reconcile_statement_arithmetic(account, p.reconciliation_tolerance)
    throughput = sum((t.amount for t in txns), ZERO)

    expected_days = (account.statement_end - account.statement_start).days + 1
    active_days = sorted({t.booking_date for t in txns})
    gap_days_uncovered = 0
    long_gaps = 0
    boundaries = [account.statement_start - timedelta(days=1), *active_days, account.statement_end + timedelta(days=1)]
    for a, b in zip(boundaries, boundaries[1:]):
        gap = (b - a).days - 1
        if gap > p.long_gap_days:
            long_gaps += 1
            gap_days_uncovered += gap
    covered_days = max(0, expected_days - gap_days_uncovered)

    source_order = sorted(txns, key=lambda t: (t.source_page or 0, t.source_line or 0))
    order_errors = sum(1 for a, b in zip(source_order, source_order[1:]) if b.booking_date < a.booking_date)

    dup_keys = Counter(
        (t.booking_date, t.direction, t.amount, t.normalized_narration, t.balance_after) for t in txns
    )
    dup_count = sum(c - 1 for c in dup_keys.values() if c > 1)
    dup_amount = sum(
        (k[2] * (c - 1) for k, c in dup_keys.items() if c > 1), ZERO
    )

    source_records = int(account.parser_metadata.get("source_record_count", n) or n)
    rejected = int(account.parser_metadata.get("rejected_record_count", 0) or 0)

    metrics: dict[str, float | str | None] = {
        "DQ01_StatementCoverageDays": safe_div(covered_days, expected_days, 0.0),
        "DQ02_TxnReconciliationPassRate": (1 - len(breaks) / eligible) if eligible else None,
        "DQ03_BalanceAvailability": safe_div(sum(1 for t in txns if t.balance_after is not None), n, 0.0),
        "DQ04_NarrationAvailability": safe_div(sum(1 for t in txns if t.raw_narration and t.raw_narration.strip()), n, 0.0),
        "DQ05_DateOrderErrorRate": safe_div(order_errors, n, 0.0),
        "DQ06_DuplicateTxnRate": safe_div(dup_count, n, 0.0),
        "DQ07_ParseLowConfidenceRate": safe_div(
            sum(1 for t in txns if t.parse_confidence < p.low_parse_confidence_threshold), n, 0.0),
        "DQ08_MissingAmountRate": safe_div(rejected, source_records, 0.0),
        "DQ09_BalanceBreakMagnitude": float(safe_div(sum(errors[t] for t in breaks), throughput, Decimal(0)))
        if throughput else 0.0,
        "DQ10_HistoryMonths": covered_days / DAYS_PER_MONTH,
        "DQ11_LongGapCount": float(long_gaps),
        "DQ12_SourceReliabilityClass": _source_reliability(account, p),
        "duplicate_amount_share": float(dup_amount / throughput) if throughput else 0.0,
        "throughput": float(throughput),
        "transaction_count": float(n),
    }

    report = AccountDataQuality(account.account_id, metrics, errors, breaks)

    pass_rate = metrics["DQ02_TxnReconciliationPassRate"]
    if pass_rate is not None and pass_rate < p.min_reconciliation_pass_rate and \
            metrics["DQ09_BalanceBreakMagnitude"] > p.max_balance_break_magnitude:
        report.hard_stop_reasons.append("UNRECONCILED_STATEMENT_ARITHMETIC")
    elif breaks:
        report.warnings.append(f"{len(breaks)} non-material balance breaks; parser remediation recommended")
    if pass_rate is None:
        report.warnings.append("NO_BALANCES: arithmetic reconciliation not possible; liquidity features degraded")
    if metrics["DQ01_StatementCoverageDays"] < p.min_statement_coverage:
        report.hard_stop_reasons.append("STATEMENT_PERIOD_MATERIALLY_INCOMPLETE")
    if metrics["duplicate_amount_share"] > p.max_duplicate_amount_share:
        report.hard_stop_reasons.append("DUPLICATE_OR_PARSE_CORRUPTION")
    if metrics["DQ08_MissingAmountRate"] > p.max_missing_amount_rate:
        report.hard_stop_reasons.append("MISSING_AMOUNTS")
    if account.currency not in p.supported_currencies:
        report.hard_stop_reasons.append("CURRENCY_NOT_VALIDATED")
    if metrics["DQ05_DateOrderErrorRate"] > p.max_date_order_error_rate:
        report.hard_stop_reasons.append("NON_DETERMINISTIC_ORDERING")
    if n == 0:
        report.hard_stop_reasons.append("NO_TRANSACTIONS")
    return report


def validate_statement_integrity(accounts: list[AccountInput], p: DataQualityParameters,
                                 has_corroborating_data: bool = False) -> DataQualityReport:
    per_account = {a.account_id: assess_account(a, p) for a in accounts}
    reasons = [f"{aid}:{r}" for aid, q in per_account.items() for r in q.hard_stop_reasons]
    warnings = [f"{aid}:{w}" for aid, q in per_account.items() for w in q.warnings]

    status: AnalysisStatus | None = None
    if any(r.endswith(("NO_TRANSACTIONS", "MISSING_AMOUNTS")) for r in reasons):
        status = AnalysisStatus.INSUFFICIENT_DATA
    elif reasons:
        status = AnalysisStatus.FAILED_DATA_QUALITY
    else:
        history = max((q.metrics["DQ10_HistoryMonths"] for q in per_account.values()), default=0.0)
        if history < p.min_history_months and not has_corroborating_data:
            reasons.append(f"HISTORY_BELOW_MINIMUM:{history:.2f}m")
            status = AnalysisStatus.INSUFFICIENT_HISTORY
    return DataQualityReport(per_account, status is not None, status, reasons, warnings)
