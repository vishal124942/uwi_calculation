"""Section 23 - Consolidated feature dictionary and feature registry (F001-F100)."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import asdict, dataclass

from se_income_engine.common.stats import mad, median
from se_income_engine.services import STEP_OF_MODULE
from se_income_engine.versions import COMPONENT_VERSIONS

_S = "se_income_engine.services."


@dataclass(frozen=True)
class FeatureRegistryEntry:
    feature_id: str
    name: str
    semantic_version: str
    level: str  # TRANSACTION | ACCOUNT_WINDOW | ACCOUNT | BORROWER | FACILITY_WINDOW
    formula_text: str
    code_reference: str
    unit: str
    null_semantics: str
    window: str | None
    dependencies: tuple[str, ...] = ()
    owner_team: str = "income-engine"
    validation_tests: tuple[str, ...] = ()
    effective_from: str = "2026-09-14T00:00:00Z"

    def as_dict(self) -> dict:
        return asdict(self)


_W = "_30D,_90D,_180D,_365D"
_ROWS = [
    ("F001", "TX_AMOUNT_LOG", "TRANSACTION", "log1p(amount)", "s23_feature_registry", "numeric", None),
    ("F002", "TX_AMOUNT_MAD_Z", "TRANSACTION", "robust amount z-score vs trailing 90d direction/channel peers", "s23_feature_registry", "numeric", None),
    ("F003", "TX_ROUNDNESS", "TRANSACTION", "closeness to configured round denominations", "s23_feature_registry", "0..1", None),
    ("F004", "TX_CHANNEL", "TRANSACTION", "normalised channel family", "s03_channel_family_normaliser", "categorical", None),
    ("F005", "TX_NARR_EMBED", "TRANSACTION", "hashed character-trigram narration embedding", "s05_narration_encoder", "vector", None),
    ("F006", "TX_REF_SIGNATURE", "TRANSACTION", "hashed structured-reference signature", "s05_identifier_extraction", "hash", None),
    ("F007", "TX_RECURRENCE", "TRANSACTION", "historical recurrence score of latent cluster", "s05_entity_resolution", "0..1", None),
    ("F008", "TX_ROLE_ENTROPY", "TRANSACTION", "normalised final role entropy", "s07_rule_overlay", "0..1", None),
    ("F009", "TX_PARSE_CONF", "TRANSACTION", "upstream parse confidence", "s03_statement_parsers", "0..1", None),
    ("F010", "TX_ENTITY_MATCH_CONF", "TRANSACTION", "latent entity match confidence", "s05_entity_resolution", "0..1/null", None),
    ("F011", "NF_OUT_24H", "TRANSACTION", "future debit sum 24h / credit amount", "s08_neighbourhood_features", "ratio", None),
    ("F012", "NF_OUT_72H", "TRANSACTION", "future debit sum 72h / credit amount", "s08_neighbourhood_features", "ratio", None),
    ("F013", "NF_MATCH_24H", "TRANSACTION", "best opposite-flow amount/time match 24h", "s08_neighbourhood_features", "0..1", None),
    ("F014", "NF_MATCH_7D", "TRANSACTION", "best opposite-flow match within 7d", "s08_neighbourhood_features", "0..1", None),
    ("F015", "NF_RETENTION_1D", "TRANSACTION", "counterfactual balance retention 1d", "s08_neighbourhood_features", "ratio", None),
    ("F016", "NF_RETENTION_3D", "TRANSACTION", "counterfactual balance retention 3d", "s08_neighbourhood_features", "ratio", None),
    ("F017", "NF_RETENTION_7D", "TRANSACTION", "counterfactual balance retention 7d", "s08_neighbourhood_features", "ratio", None),
    ("F018", "NF_NORMAL_SPEND_SHARE", "TRANSACTION", "subsequent matched OPEX share", "s08_neighbourhood_features", "ratio", None),
    ("F019", "NF_TRANSFER_SHARE", "TRANSACTION", "subsequent transfer/pass-through share", "s08_neighbourhood_features", "ratio", None),
    ("F020", "NF_RECYCLING_SCORE", "TRANSACTION", "repeated reciprocal motif score", "s08_neighbourhood_features", "0..1", None),
    ("F021", "EOC", "ACCOUNT_WINDOW", "sum amount*P(eligible operating credit)", "s10_operating_inflow_reconstruction", "currency", _W),
    ("F022", "EOC_HC", "ACCOUNT_WINDOW", "high-confidence operating collections", "s10_operating_inflow_reconstruction", "currency", _W),
    ("F023", "EOC_RATIO", "ACCOUNT_WINDOW", "EOC/gross credits", "s10_operating_inflow_reconstruction", "ratio", _W),
    ("F024", "EOC_ACTIVE_DAYS", "ACCOUNT_WINDOW", "days with material expected operating receipt", "s10_operating_inflow_reconstruction", "count", _W),
    ("F025", "EOC_COUNT", "ACCOUNT_WINDOW", "weighted operating receipt count", "s10_operating_inflow_reconstruction", "count", _W),
    ("F026", "EOC_MEDIAN_TICKET", "ACCOUNT_WINDOW", "weighted median operating receipt", "s10_operating_inflow_reconstruction", "currency", _W),
    ("F027", "EOC_TICKET_MAD", "ACCOUNT_WINDOW", "weighted robust dispersion", "s10_operating_inflow_reconstruction", "currency", _W),
    ("F028", "EOC_TOP1_SHARE", "ACCOUNT_WINDOW", "largest operating receipt/EOC", "s10_operating_inflow_reconstruction", "ratio", _W),
    ("F029", "EOC_TOP5_SHARE", "ACCOUNT_WINDOW", "top five/EOC", "s10_operating_inflow_reconstruction", "ratio", _W),
    ("F030", "EOC_REPEAT_SHARE", "ACCOUNT_WINDOW", "recurring-pattern operating collections/EOC", "s10_operating_inflow_reconstruction", "ratio", _W),
    ("F031", "DIRECT_COST", "ACCOUNT_WINDOW", "sum amount*P(D01)", "s11_operating_outflow_reconstruction", "currency", _W),
    ("F032", "PAYROLL", "ACCOUNT_WINDOW", "sum amount*P(D02)", "s11_operating_outflow_reconstruction", "currency", _W),
    ("F033", "FIXED_OPEX", "ACCOUNT_WINDOW", "sum eligible D03-D06 components", "s11_operating_outflow_reconstruction", "currency", _W),
    ("F034", "STATUTORY_CASH", "ACCOUNT_WINDOW", "sum amount*P(D07)", "s11_operating_outflow_reconstruction", "currency", _W),
    ("F035", "COR", "ACCOUNT_WINDOW", "core operating requirement", "s11_operating_outflow_reconstruction", "currency", _W),
    ("F036", "DIRECT_COST_RATIO", "ACCOUNT_WINDOW", "DIRECT_COST/EOC", "s11_operating_outflow_reconstruction", "ratio", _W),
    ("F037", "PAYROLL_RATIO", "ACCOUNT_WINDOW", "PAYROLL/EOC", "s11_operating_outflow_reconstruction", "ratio", _W),
    ("F038", "FIXED_COST_RATIO", "ACCOUNT_WINDOW", "FIXED_OPEX/EOC", "s11_operating_outflow_reconstruction", "ratio", _W),
    ("F039", "CAPEX", "ACCOUNT_WINDOW", "sum amount*P(D10)", "s11_operating_outflow_reconstruction", "currency", _W),
    ("F040", "MAINT_CAPEX", "ACCOUNT_WINDOW", "sum amount*P(D11)", "s11_operating_outflow_reconstruction", "currency", _W),
    ("F041", "ROC", "ACCOUNT_WINDOW", "EOC-COR (monthly-equivalent, full period)", "s21_income_normalisation", "currency", None),
    ("F042", "ROC_MARGIN", "ACCOUNT_WINDOW", "ROC/EOC", "s21_income_normalisation", "ratio", None),
    ("F043", "POS_ROC_MONTH_RATIO", "ACCOUNT", "positive ROC months/observed months", "s18_trend_seasonality", "ratio", None),
    ("F044", "ROC_MAD", "ACCOUNT", "MAD monthly ROC", "s18_trend_seasonality", "currency", None),
    ("F045", "ROC_P20", "ACCOUNT", "20th percentile cycle-adjusted ROC", "s21_income_normalisation", "currency", None),
    ("F046", "WORST_90", "ACCOUNT", "worst rolling-90 monthly equivalent", "s21_income_normalisation", "currency", None),
    ("F047", "ROC_SLOPE", "ACCOUNT", "robust monthly slope", "s18_trend_seasonality", "currency/month", None),
    ("F048", "EOC_SLOPE", "ACCOUNT", "robust EOC slope", "s18_trend_seasonality", "currency/month", None),
    ("F049", "RECENT_DECLINE", "ACCOUNT", "recent deterioration score", "s18_trend_seasonality", "0..1", None),
    ("F050", "SEASONALITY_STRENGTH", "ACCOUNT", "repeatable seasonality score", "s18_trend_seasonality", "0..1", None),
    ("F051", "CYCLE_LAG_OUT_IN", "ACCOUNT", "qualified peak DO->OI lag", "s13_working_capital_cycle_engine", "days/null", None),
    ("F052", "CYCLE_LAG_IN_OUT", "ACCOUNT", "qualified peak OI->DO lag", "s13_working_capital_cycle_engine", "days/null", None),
    ("F053", "CYCLE_CORR", "ACCOUNT", "peak robust cross-correlation", "s13_working_capital_cycle_engine", "-1..1", None),
    ("F054", "CYCLE_PROMINENCE", "ACCOUNT", "peak prominence vs neighbouring lags", "s13_working_capital_cycle_engine", "numeric", None),
    ("F055", "CYCLE_STABILITY", "ACCOUNT", "rolling lag stability", "s13_working_capital_cycle_engine", "0..1", None),
    ("F056", "BUILD_SCORE", "ACCOUNT", "current build-up proxy", "s13_working_capital_cycle_engine", "0..bounded", None),
    ("F057", "LIQUIDATION_SCORE", "ACCOUNT", "current liquidation proxy", "s13_working_capital_cycle_engine", "0..bounded", None),
    ("F058", "CAOCG", "ACCOUNT_WINDOW", "cycle-adjusted operating cash generation", "s21_income_normalisation", "currency", None),
    ("F059", "OPERATING_LIQUIDITY_NEED", "ACCOUNT", "historical cycle liquidity requirement", "s13_working_capital_cycle_engine", "currency", None),
    ("F060", "CYCLE_EVIDENCE_QUALITY", "ACCOUNT", "signal/history quality", "s13_working_capital_cycle_engine", "0..1", None),
    ("F061", "ADB", "ACCOUNT_WINDOW", "average daily balance", "s14_balance_liquidity_engine", "currency", None),
    ("F062", "MDB", "ACCOUNT_WINDOW", "median daily balance", "s14_balance_liquidity_engine", "currency", None),
    ("F063", "P10_BALANCE", "ACCOUNT_WINDOW", "10th percentile daily balance", "s14_balance_liquidity_engine", "currency", None),
    ("F064", "MIN_BALANCE", "ACCOUNT_WINDOW", "minimum daily balance", "s14_balance_liquidity_engine", "currency", None),
    ("F065", "LOW_LIQ_DAYS", "ACCOUNT_WINDOW", "low-liquidity day count", "s14_balance_liquidity_engine", "count", None),
    ("F066", "BAL_RECOVERY_DAYS", "ACCOUNT", "median trough recovery time", "s14_balance_liquidity_engine", "days", None),
    ("F067", "BAL_TREND", "ACCOUNT", "robust weekly balance slope", "s14_balance_liquidity_engine", "currency/time", None),
    ("F068", "LIQ_BUFFER_COR", "ACCOUNT", "median balance/monthly-equivalent COR", "s14_balance_liquidity_engine", "ratio", None),
    ("F069", "OD_UTIL_MEAN", "FACILITY_WINDOW", "mean OD/CC utilisation", "s14_balance_liquidity_engine", "ratio/null", None),
    ("F070", "OD_UTIL_P90", "FACILITY_WINDOW", "p90 utilisation", "s14_balance_liquidity_engine", "ratio/null", None),
    ("F071", "FIN_CREDIT", "ACCOUNT_WINDOW", "sum amount*P(C05)", "s15_financing_debt_service", "currency", _W),
    ("F072", "FIN_CREDIT_RATIO", "ACCOUNT_WINDOW", "FIN_CREDIT/gross credits", "s15_financing_debt_service", "ratio", _W),
    ("F073", "DEBT_INTEREST", "ACCOUNT_WINDOW", "sum amount*P(D08)", "s15_financing_debt_service", "currency", _W),
    ("F074", "DEBT_PRINCIPAL", "ACCOUNT_WINDOW", "sum amount*P(D09)", "s15_financing_debt_service", "currency", _W),
    ("F075", "EXT_FUND_DEP", "ACCOUNT", "funded operating outflow / COR", "s15_financing_debt_service", "ratio", None),
    ("F076", "RAPID_RECYCLE", "ACCOUNT", "rapid recycled mass/gross credits", "s19_anomaly_detection", "ratio", None),
    ("F077", "EXCEPTIONAL_DEP", "ACCOUNT", "exceptional credits dependence", "s19_anomaly_detection", "ratio", None),
    ("F078", "ROUND_FLOW_CONC", "ACCOUNT", "round-flow concentration", "s19_anomaly_detection", "ratio", None),
    ("F079", "PREAPP_SURGE", "ACCOUNT", "pre-application activity surge", "s19_anomaly_detection", "numeric", None),
    ("F080", "NEW_PATTERN_SURGE", "ACCOUNT", "recent unseen-pattern share", "s19_anomaly_detection", "ratio", None),
    ("F081", "OWNER_DRAW", "ACCOUNT_WINDOW", "sum amount*P(D12)", "s16_owner_extraction", "currency", _W),
    ("F082", "OWNER_DRAW_MEDIAN", "ACCOUNT", "median monthly owner draw", "s16_owner_extraction", "currency", None),
    ("F083", "OWNER_DRAW_FUND_QUALITY", "ACCOUNT", "draws supported by operating cash", "s16_owner_extraction", "0..1", None),
    ("F084", "DRAW_TO_SBCI", "ACCOUNT", "owner draw/SBCI", "s16_owner_extraction", "ratio", None),
    ("F085", "OWN_TRANSFER_MASS", "ACCOUNT", "probable unsupplied own-account transfer mass", "s17_multi_account_consolidation", "currency", None),
    ("F086", "CASH_INTENSITY", "ACCOUNT", "business cash flows/(EOC+COR)", "s20_coverage_observability", "ratio", None),
    ("F087", "UNKNOWN_CREDIT_MASS", "ACCOUNT", "amount-weighted credit uncertainty", "s10_operating_inflow_reconstruction", "ratio", None),
    ("F088", "UNKNOWN_DEBIT_MASS", "ACCOUNT", "amount-weighted debit uncertainty", "s11_operating_outflow_reconstruction", "ratio", None),
    ("F089", "COVERAGE_RISK", "ACCOUNT", "coverage evidence class", "s20_coverage_observability", "categorical", None),
    ("F090", "LEGAL_ATTRIB_CONF", "BORROWER", "legal attribution confidence", "s16_legal_attribution", "0..1", None),
    ("F091", "HISTORY_MONTHS", "ACCOUNT", "complete history months", "s04_statement_integrity_gate", "numeric", None),
    ("F092", "RECON_PASS", "ACCOUNT", "statement arithmetic pass rate", "s04_statement_integrity_gate", "ratio", None),
    ("F093", "BAL_AVAIL", "ACCOUNT", "balance availability", "s04_statement_integrity_gate", "ratio", None),
    ("F094", "PARSE_LOW_CONF", "ACCOUNT", "low-parse-confidence share", "s04_statement_integrity_gate", "ratio", None),
    ("F095", "ROLE_UNCERTAINTY", "ACCOUNT", "amount-weighted role entropy", "s22_uncertainty_confidence", "0..1", None),
    ("F096", "ARCHETYPE_CONF", "ACCOUNT", "archetype probability", "s09_archetype_inference", "0..1", None),
    ("F097", "CROSS_VIEW_CONSISTENCY", "ACCOUNT", "agreement of cash/liquidity/draw/external views", "s22_uncertainty_confidence", "0..1", None),
    ("F098", "DATA_INTEGRITY_CONF", "ACCOUNT", "data-quality composite", "s22_uncertainty_confidence", "0..1", None),
    ("F099", "INCOME_MODEL_CONF", "ACCOUNT", "calibrated income confidence", "s22_uncertainty_confidence", "0..1", None),
    ("F100", "PRED_INTERVAL_WIDTH", "ACCOUNT", "prediction interval width/central estimate", "s22_uncertainty_confidence", "ratio", None),
]

FEATURE_REGISTRY: dict[str, FeatureRegistryEntry] = {
    fid: FeatureRegistryEntry(
        feature_id=fid, name=name, semantic_version="1.0.0", level=level, formula_text=formula,
        code_reference=f"{_S}{STEP_OF_MODULE[module]}.{module}", unit=unit,
        null_semantics="null = not computable from available evidence (never zero-filled)",
        window=window,
    )
    for fid, name, level, formula, module, unit, window in _ROWS
}
REGISTRY_VERSION = COMPONENT_VERSIONS["feature_registry"]

# Totals keys used for windowed feature materialisation.
_WINDOW_TOTALS = {
    "F021": "eoc", "F022": "eoc_hc", "F031": "direct_cost", "F032": "payroll", "F034": "statutory", "F035": "cor",
    "F039": "capex", "F040": "maintenance_capex", "F071": "financing_in", "F073": "debt_interest",
    "F074": "debt_principal", "F081": "owner_draw",
}
_WINDOW_INFLOW = {
    "F023": "IN05_OperatingCreditRatio", "F024": "IN07_OperatingActiveDays", "F025": "IN08_OperatingReceiptCount",
    "F026": "IN09_MedianOperatingTicket", "F027": "IN10_OperatingTicketMAD", "F028": "IN11_TopReceiptShare",
    "F029": "IN12_Top5ReceiptShare", "F030": "IN13_RepeatPatternShare",
}
_WINDOW_OUTFLOW = {"F033": "OUT03_FixedOpex", "F036": "OUT06_DirectCostToEOC", "F037": "OUT07_PayrollToEOC",
                   "F038": "OUT08_FixedCostToEOC"}


def _roundness(amount: float) -> float:
    for denom, score in ((1000, 1.0), (500, 0.75), (100, 0.5), (10, 0.25)):
        if amount >= denom and amount % denom == 0:
            return score
    return 0.0


def transaction_feature_rows(ctx) -> dict[str, dict[str, object]]:
    """F001-F020 per transaction."""
    peers: dict[tuple, list[tuple]] = defaultdict(list)
    for t in ctx.txns:
        peers[(t.account_id, t.direction, t.channel_family, t.booking_date.year, t.booking_date.month)].append(float(t.amount))
    peer_stats = {}
    for t in ctx.txns:
        key = (t.account_id, t.direction, t.channel_family)
        month_key = (t.booking_date.year, t.booking_date.month)
        if (key, month_key) in peer_stats:
            continue
        window = []
        y, m = month_key
        for back in range(3):
            mm, yy = m - back, y
            while mm <= 0:
                mm += 12
                yy -= 1
            window += peers.get((*key, yy, mm), [])
        peer_stats[(key, month_key)] = (median(window), mad(window))

    history = max(1.0, ctx.account_features.history_months) if ctx.account_features else 1.0
    rows = {}
    for t in ctx.txns:
        amt = float(t.amount)
        med, spread = peer_stats[((t.account_id, t.direction, t.channel_family), (t.booking_date.year, t.booking_date.month))]
        z = (amt - med) / (1.4826 * spread) if spread else None
        hyp = ctx.hypotheses[t.transaction_id]
        cs = ctx.cluster_stats.get(hyp.cluster_id)
        nf = ctx.neighbourhood[t.transaction_id]
        rows[t.transaction_id] = {
            "F001": math.log1p(amt),
            "F002": z,
            "F003": _roundness(amt),
            "F004": t.channel_family.value,
            "F005": len(ctx.text_features.get(t.transaction_id, {})),
            "F006": ctx.identifiers[t.transaction_id].reference_signature,
            "F007": min(1.0, len(cs.active_months) / history) if cs and cs.count > 1 else 0.0,
            "F008": ctx.predictions[t.transaction_id].entropy,
            "F009": t.parse_confidence,
            "F010": hyp.match_probability if hyp.match_probability else None,
            "F011": nf.NF01_CreditOutflow24h,
            "F012": nf.NF02_CreditOutflow72h,
            "F013": nf.NF03_AmountMatchedOut24h,
            "F014": nf.NF04_AmountMatchedOut7d,
            "F015": nf.NF06_BalanceRetention1d,
            "F016": nf.NF07_BalanceRetention3d,
            "F017": nf.NF08_BalanceRetention7d,
            "F018": nf.NF09_NormalSpendShareAfterCredit,
            "F019": nf.NF10_TransferLikeShareAfterCredit,
            "F020": nf.NF12_FlowRecyclingScore,
        }
    return rows


def materialise_feature_vector(ctx) -> dict[str, object]:
    """Account/borrower-level feature values F021-F100 (windowed features carry _<window> suffixes)."""
    af = ctx.account_features
    out: dict[str, object] = {}
    for label, w in af.windows.items():
        for fid, key in _WINDOW_TOTALS.items():
            out[f"{fid}_{label}"] = float(w.totals[key])
        for fid, key in _WINDOW_INFLOW.items():
            out[f"{fid}_{label}"] = w.inflow.get(key)
        for fid, key in _WINDOW_OUTFLOW.items():
            out[f"{fid}_{label}"] = w.outflow.get(key)
        out[f"F072_{label}"] = float(w.totals["financing_in"] / w.totals["gross_credits"]) if w.totals["gross_credits"] else None

    tr, wc, bal = ctx.trend.features, ctx.cycle.features, ctx.liquidity.features
    an, own, cv = ctx.anomalies.features, ctx.owner.features, ctx.coverage.features
    dq_vals = [q.metrics for q in ctx.dq.accounts.values()]
    unc = ctx.uncertainty
    out.update({
        "F041": ctx.sbci.features.get("F041_ROC"),
        "F042": ctx.sbci.features.get("F042_ROC_MARGIN"),
        "F043": tr.get("TR06_PositiveROCMonthRatio"),
        "F044": tr.get("TR07_ROCMAD"),
        "F045": ctx.sbci.features.get("F045_ROC_P20"),
        "F046": ctx.sbci.features.get("F046_WORST_90"),
        "F047": tr.get("TR05_RobustROCSlope"),
        "F048": tr.get("TR04_RobustEOCSlope"),
        "F049": tr.get("TR11_RecentDeteriorationScore"),
        "F050": tr.get("TR10_SeasonalityStrength"),
        "F051": wc.get("WC01_PeakOutflowToInflowLag"),
        "F052": wc.get("WC02_PeakInflowToOutflowLag"),
        "F053": wc.get("WC03_CycleCorrelation"),
        "F054": wc.get("WC04_CycleProminence"),
        "F055": wc.get("WC05_CycleStability"),
        "F056": wc.get("WC06_BuildScore"),
        "F057": wc.get("WC07_LiquidationScore"),
        "F058": ctx.sbci.features.get("F058_CAOCG"),
        "F059": wc.get("WC09_OperatingLiquidityNeed"),
        "F060": wc.get("WC14_CycleEvidenceQuality"),
        "F061": bal.get("BAL01_AverageDailyBalance"),
        "F062": bal.get("BAL02_MedianDailyBalance"),
        "F063": bal.get("BAL03_P10Balance"),
        "F064": bal.get("BAL04_MinimumBalance"),
        "F065": bal.get("BAL06_LowLiquidityDays"),
        "F066": bal.get("BAL08_BalanceRecoveryMedian"),
        "F067": bal.get("BAL10_BalanceTrend180"),
        "F068": bal.get("BAL11_LiquidityBufferToCOR"),
        "F069": bal.get("OD_UTIL_MEAN"),
        "F070": bal.get("OD_UTIL_P90"),
        "F075": ctx.financing.features.get("FIN05_ExternalFundingDependency"),
        "F076": an.get("AN03_RapidRecyclingRatio"),
        "F077": an.get("AN06_ExceptionalCreditDependency"),
        "F078": an.get("AN04_RoundAmountConcentration"),
        "F079": an.get("AN01_PreApplicationCreditSurge"),
        "F080": an.get("AN12_NewPatternSurge"),
        "F082": own.get("OWN02_OwnerDrawMedianMonthly"),
        "F083": own.get("OWN05_OwnerDrawFundingQuality"),
        "F084": own.get("OWN06_DrawToSBCIRatio"),
        "F085": ctx.multi_account.get("MA02_UnmatchedOwnTransferSuspicion"),
        "F086": cv.get("CV02_CashIntensity"),
        "F087": af.full_period.inflow.get("IN14_UnknownCreditEconomicMass"),
        "F088": af.full_period.outflow.get("OUT14_UnknownDebitEconomicMass"),
        "F089": cv.get("CV09_CoverageRisk"),
        "F090": ctx.legal.confidence,
        "F091": max(m["DQ10_HistoryMonths"] for m in dq_vals),
        "F092": min((m["DQ02_TxnReconciliationPassRate"] for m in dq_vals
                     if m["DQ02_TxnReconciliationPassRate"] is not None), default=None),
        "F093": min(m["DQ03_BalanceAvailability"] for m in dq_vals),
        "F094": max(m["DQ07_ParseLowConfidenceRate"] for m in dq_vals),
        "F095": ctx.role_uncertainty,
        "F096": ctx.archetype.probability,
        "F097": unc.dimensions["CF08_CrossViewConsistency"],
        "F098": unc.dimensions["CF01_DataIntegrity"],
        "F099": unc.confidence,
        "F100": float((unc.upper - unc.lower) / unc.central) if unc.central else None,
    })
    return out
