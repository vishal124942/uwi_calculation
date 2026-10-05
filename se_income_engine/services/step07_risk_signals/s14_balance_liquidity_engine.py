"""Section 14 - Balance and liquidity engine (BAL01-BAL12). Balance is corroborative, never an income formula."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from se_income_engine.common.stats import (
    DAYS_PER_MONTH,
    mean,
    median,
    quantile,
    safe_div,
    stdev,
    theil_sen_slope,
)
from se_income_engine.contracts.account import AccountInput
from se_income_engine.contracts.enums import AccountType
from se_income_engine.services.step03_transaction_evidence.s08_neighbourhood_features import NeighbourhoodFeatures
from se_income_engine.services.step06_aggregation_archetype_cash.s10_s11_window_aggregation import AccountFeatures


@dataclass
class DailyBalance:
    account_id: str
    day: date
    balance: Decimal
    imputed: bool


@dataclass
class LiquidityResult:
    features: dict[str, float | None]
    daily: dict[str, list[DailyBalance]]
    consolidated_daily: list[tuple[date, float]] = field(default_factory=list)


def daily_balance_series(account: AccountInput, end: date) -> list[DailyBalance]:
    """End-of-day balances; days without transactions are forward-filled and tagged as imputed."""
    txns = [t for t in account.transactions if t.balance_after is not None]
    if not txns:
        return []
    eod: dict[date, Decimal] = {}
    for t in txns:
        eod[t.booking_date] = t.balance_after
    out = []
    first = txns[0]
    current = first.balance_before if first.balance_before is not None else first.balance_after
    d = account.statement_start
    while d <= min(end, account.statement_end):
        if d in eod:
            current = eod[d]
            out.append(DailyBalance(account.account_id, d, current, False))
        else:
            out.append(DailyBalance(account.account_id, d, current, True))
        d += timedelta(days=1)
    return out


def _recovery_days(values: list[float]) -> float | None:
    if len(values) < 10:
        return None
    p10, med = quantile(values, 0.1), median(values)
    recoveries = []
    i = 0
    while i < len(values):
        if values[i] <= p10:
            j = i
            while j < len(values) and values[j] < med:
                j += 1
            if j < len(values):
                recoveries.append(j - i)
            i = j + 1
        else:
            i += 1
    return median(recoveries)


def compute_balance_liquidity(accounts: list[AccountInput], af: AccountFeatures,
                              nf: dict[str, NeighbourhoodFeatures]) -> LiquidityResult:
    daily = {a.account_id: daily_balance_series(a, af.as_of) for a in accounts}
    deposit_accounts = [a for a in accounts if a.account_type not in (AccountType.OD, AccountType.CC)]
    od_accounts = [a for a in accounts if a.account_type in (AccountType.OD, AccountType.CC)]

    consolidated: dict[date, float] = {}
    for a in deposit_accounts:
        for db in daily[a.account_id]:
            consolidated[db.day] = consolidated.get(db.day, 0.0) + float(db.balance)
    series = sorted(consolidated.items())
    values = [v for _, v in series]

    cor_monthly = float(af.full_period.monthly("cor"))
    daily_cor = cor_monthly / DAYS_PER_MONTH if cor_monthly else 0.0
    low_threshold = max(100.0, daily_cor)

    recent_90 = [v for d, v in series if d > af.as_of - timedelta(days=90)]
    recent_180 = [v for d, v in series if d > af.as_of - timedelta(days=180)]

    def slope(vals: list[float]) -> float | None:
        weekly = [median(vals[i:i + 7]) for i in range(0, len(vals), 7)]
        if len(weekly) < 4:
            return None
        return theil_sen_slope(list(range(len(weekly))), weekly)

    utilisation, near_limit, breaches = [], 0, 0
    for a in od_accounts:
        if not a.sanctioned_limit:
            continue
        limit = float(a.sanctioned_limit)
        dp = float(a.drawing_power) if a.drawing_power else limit
        for db in daily[a.account_id]:
            used = max(0.0, -float(db.balance))
            utilisation.append(used / limit)
            if used >= 0.9 * limit:
                near_limit += 1
            if used > min(limit, dp):
                breaches += 1

    retention = {1: [], 3: [], 7: []}
    weights = []
    for ln in af.ledger.values():
        if not ln.is_credit or ln.p_operating <= 0:
            continue
        f = nf[ln.txn_id]
        if f.NF06_BalanceRetention1d is None:
            continue
        weights.append(ln.p_operating * float(ln.amount))
        retention[1].append(f.NF06_BalanceRetention1d)
        retention[3].append(f.NF07_BalanceRetention3d)
        retention[7].append(f.NF08_BalanceRetention7d)

    def wavg(vals):
        tw = sum(weights)
        return sum(v * w for v, w in zip(vals, weights)) / tw if tw and vals else None

    m = mean(values)
    sd = stdev(values)
    neg_days = sum(1 for v in values if v < 0)
    features = {
        "BAL01_AverageDailyBalance": m,
        "BAL02_MedianDailyBalance": median(values),
        "BAL03_P10Balance": quantile(values, 0.1),
        "BAL04_MinimumBalance": min(values) if values else None,
        "BAL05_BalanceCV": (sd / abs(m)) if sd is not None and m and abs(m) > 1.0 else None,
        "BAL06_LowLiquidityDays": float(sum(1 for v in values if v < low_threshold)),
        "BAL07_NearLimitDays": float(near_limit) if od_accounts else None,
        "BAL08_BalanceRecoveryMedian": _recovery_days(values),
        "BAL09_ReceiptRetention1d": wavg(retention[1]),
        "BAL09_ReceiptRetention3d": wavg(retention[3]),
        "BAL09_ReceiptRetention7d": wavg(retention[7]),
        "BAL10_BalanceTrend90": slope(recent_90),
        "BAL10_BalanceTrend180": slope(recent_180),
        "BAL11_LiquidityBufferToCOR": safe_div(median(values) or 0.0, cor_monthly, None),
        "BAL12_NegativeBalanceStress": safe_div(neg_days, len(values), None),
        "OD_UTIL_MEAN": mean(utilisation),
        "OD_UTIL_P90": quantile(utilisation, 0.9),
        "LIMIT_BREACH_COUNT": float(breaches) if od_accounts else None,
        "MA09_ConsolidatedBalanceLiquidity": median(values),
        "low_liquidity_threshold": low_threshold,
        "imputed_day_share": safe_div(sum(1 for s in daily.values() for d in s if d.imputed),
                                      sum(len(s) for s in daily.values()), None),
    }
    return LiquidityResult(features, daily, series)
