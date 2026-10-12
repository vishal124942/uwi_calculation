"""Section 11 - Operating outflow reconstruction (COR and OUT01-OUT14).

COR_W = sum amount_j * [P(D01..D06) + tax_basis * P(D07)]
Debt principal, owner draw, internal transfer, personal expense, capex and pass-through remittance are
never part of COR. Interest is reported separately (Section 11.1).
"""

from __future__ import annotations

from decimal import Decimal

from se_income_engine.common.money import ZERO
from se_income_engine.common.stats import safe_div, weighted_median
from se_income_engine.contracts.entity import EntityHypothesis
from se_income_engine.contracts.enums import IdentityStatus
from se_income_engine.services.m2_role_classifier.s05_entity_resolution import ClusterStatistics

CORE_DEBIT_ROLES = ("D01", "D02", "D03", "D04", "D05", "D06")


def compute_outflow_features(lines: list, totals: dict[str, Decimal], months: float,
                             hypotheses: dict[str, EntityHypothesis], cluster_stats: dict[str, ClusterStatistics],
                             gross_debits: Decimal, daily_materiality: Decimal = Decimal("100")) -> dict[str, float | None]:
    debit_lines = [ln for ln in lines if not ln.is_credit]
    eoc = float(totals["eoc"])
    cor = float(totals["cor"])
    daily: dict = {}
    recurring = ZERO
    amounts, weights = [], []
    for ln in debit_lines:
        core = ln.buckets["cor_debit"]
        if core <= 0:
            continue
        daily[ln.booking_date] = daily.get(ln.booking_date, ZERO) + core
        hyp = hypotheses[ln.txn_id]
        cs = cluster_stats.get(hyp.cluster_id)
        if cs and hyp.identity_status != IdentityStatus.UNRESOLVED and len(cs.debit_months) >= 2 and cs.debit_count >= 3:
            recurring += core
        amounts.append(float(ln.amount))
        weights.append(float(core / ln.amount))
    wm = weighted_median(amounts, weights)
    unknown_mass = sum((ln.amount * Decimal(repr(ln.uncertainty)) for ln in debit_lines), ZERO)
    fixed = totals["rent"] + totals["utilities"] + totals["logistics"] + totals["other_opex"]
    maint_monthly = float(totals["maintenance_capex"]) / months if months else 0.0
    eoc_monthly = eoc / months if months else 0.0
    return {
        "OUT01_DirectCost": float(totals["direct_cost"]),
        "OUT02_Payroll": float(totals["payroll"]),
        "OUT03_FixedOpex": float(fixed),
        "OUT04_StatutoryCash": float(totals["statutory"]),
        "OUT05_CoreOpRequirement": cor,
        "OUT06_DirectCostToEOC": safe_div(float(totals["direct_cost"]), eoc, None),
        "OUT07_PayrollToEOC": safe_div(float(totals["payroll"]), eoc, None),
        "OUT08_FixedCostToEOC": safe_div(float(fixed), eoc, None),
        "OUT09_OpActiveDays": float(sum(1 for v in daily.values() if v >= daily_materiality)),
        "OUT10_RecurringOutflowShare": safe_div(float(recurring), cor, None),
        "OUT11_OutflowTicketMAD": weighted_median([abs(a - wm) for a in amounts], weights) if wm is not None else None,
        "OUT12_CapexIntensity": safe_div(float(totals["capex"]), eoc, None),
        "OUT13_MaintenanceCapexRate": safe_div(maint_monthly, eoc_monthly, None),
        "OUT14_UnknownDebitEconomicMass": safe_div(float(unknown_mass), float(gross_debits), None),
    }
