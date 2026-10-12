"""Section 27.1 unit tests UT-01 .. UT-15."""

from __future__ import annotations

import dataclasses
import re
from datetime import date, timedelta
from decimal import Decimal

import pytest

from builders import HOLDER, StatementBuilder, business, make_request
from se_income_engine.config.parameters import DEFAULT_PARAMETERS
from se_income_engine.contracts.enums import (AnalysisStatus, CycleStatus, LegalAttributionStatus, LegalOwnerType,
                                              PairEdgeType)
from se_income_engine.pipeline.analyse import run_analysis_pipeline
from se_income_engine.services.m1_parser_normaliser.s03_transaction_canonicalisation import canonicalize_account
from se_income_engine.services.supporting.dq_integrity_gate.s04_statement_integrity_gate import reconcile_statement_arithmetic


def run(*accounts, **kw):
    return run_analysis_pipeline(make_request(*accounts, **kw))


def monthly(ctx, key: str) -> float:
    return float(ctx.account_features.full_period.monthly(key))


def total(ctx, key: str) -> float:
    return float(ctx.account_features.full_period.totals[key])


@pytest.fixture(scope="module")
def baseline():
    return run(business().build())


def test_ut01_balance_arithmetic_reconciles_exactly():
    account = canonicalize_account(business(months=3).build())
    errors, breaks, eligible = reconcile_statement_arithmetic(account, Decimal("0.05"))
    assert eligible == len(account.transactions) - 1
    assert breaks == []
    assert all(e == 0 for e in errors.values())

    broken = business(months=3).build()
    broken.transactions[50].balance_after += Decimal("1000")
    _, breaks, _ = reconcile_statement_arithmetic(canonicalize_account(broken), Decimal("0.05"))
    assert breaks, "a material balance break must be reported, not absorbed"


def test_ut02_missing_narration_produces_valid_probabilities():
    b = business(months=4)
    for row in b.rows[::3]:
        row.narration = None
    ctx = run(b.build())
    blank = [t for t in ctx.txns if not t.raw_narration]
    assert blank
    for t in blank:
        probs = ctx.predictions[t.transaction_id].final_probabilities
        assert abs(sum(probs.values()) - 1.0) < 1e-9
        assert all(0.0 <= v <= 1.0 for v in probs.values())


def test_ut03_internal_transfer_excluded_exactly_once():
    a = business(seed=11, account_id="ACC1", masked_account="XXXXXX1234")
    b = business(seed=12, account_id="ACC2", masked_account="XXXXXX5678")
    transfer_day = date(2025, 6, 10)
    a.debit(transfer_day, 75000, f"NEFT/N{a.rrn()}/{HOLDER}/TRF TO A/C XXXXXX5678", "NEFT",
            f"Fund Transfer to {HOLDER}")
    b.credit(transfer_day, 75000, f"NEFT/N{b.rrn()}/{HOLDER}/FROM A/C XXXXXX1234", "NEFT",
             f"Fund Transfer from {HOLDER}")
    ctx = run(a.build(), b.build())

    edges = [e for e in ctx.internal_edges if e.edge_type == PairEdgeType.INTERNAL_TRANSFER]
    matched = [e for e in edges if ctx.predictions[e.credit_txn_id].final_probabilities["C04"] == 1.0
               and next(t for t in ctx.txns if t.transaction_id == e.credit_txn_id).amount == Decimal("75000")]
    assert len(matched) == 1
    e = matched[0]
    ids = [x for x in ctx.pair_graph.edges if e.credit_txn_id in (x.credit_txn_id, x.debit_txn_id)]
    assert len(ids) == 1, "transfer leg must appear in exactly one edge"
    line = ctx.account_features.ledger[e.credit_txn_id]
    assert line.buckets["eoc_credit"] == 0
    assert ctx.account_features.ledger[e.debit_txn_id].buckets["cor_debit"] == 0


def test_ut04_explicit_loan_credit_does_not_increase_eoc(baseline):
    b = business()
    b.credit(date(2025, 7, 5), 500000, "LOAN DISBURSAL A/C 99887766 BAJAJ FINANCE", "NEFT", "Loan Disbursal")
    ctx = run(b.build())
    assert total(ctx, "financing_in") >= 500000 * 0.99
    assert abs(total(ctx, "eoc") - total(baseline, "eoc")) < 500000 * 0.01


@pytest.mark.parametrize("share", [0.35, 0.2])
def test_ut05_emi_split_follows_configured_interest_share(share):
    b = business(months=4)
    for m in range(1, 5):
        b.debit(date(2025, m, 5), 12000, f"ACH/BAJAJ FINANCE EMI/UMRN{100000 + m}", "NACH", "EMI")
    params = dataclasses.replace(DEFAULT_PARAMETERS, roles=dataclasses.replace(DEFAULT_PARAMETERS.roles,
                                                                               emi_interest_share=share))
    ctx = run_analysis_pipeline(make_request(b.build()), params)
    emis = [t for t in ctx.txns if "EMI" in (t.raw_narration or "")]
    assert len(emis) == 4
    for t in emis:
        p = ctx.predictions[t.transaction_id].final_probabilities
        assert p["D08"] == pytest.approx(share)
        assert p["D09"] == pytest.approx(1 - share)
        assert ctx.account_features.ledger[t.transaction_id].buckets["cor_debit"] == 0


def test_ut06_credit_then_reversal_does_not_inflate_eoc(baseline):
    b = business()
    b.credit(date(2025, 8, 4), 180000, f"NEFT/N{b.rrn()}/VIKAS ENTERPRISES/ICIC0004321", "NEFT",
             "Fund Transfer from VIKAS ENTERPRISES")
    b.debit(date(2025, 8, 6), 180000, f"REVERSAL NEFT/N{b.rrn()}/VIKAS ENTERPRISES RETURN", "NEFT", "Reversal")
    ctx = run(b.build())
    assert any(e.edge_type == PairEdgeType.REVERSAL for e in ctx.pair_graph.edges)
    assert total(ctx, "eoc") - total(baseline, "eoc") < 180000 * 0.05


def test_ut07_cash_deposit_is_probabilistic():
    b = business(months=6)
    deposits = []
    for m in range(1, 7):
        for day in (5, 12, 19, 26):
            b.credit(date(2025, m, day), 20000, "BY CASH BRANCH 0042", "Cash-Bank Branch", "Cash Deposit")
            deposits.append((date(2025, m, day), 20000))
    ctx = run(b.build())
    cash = [t for t in ctx.txns if "BY CASH" in (t.raw_narration or "")]
    assert len(cash) == len(deposits)
    for t in cash:
        line = ctx.account_features.ledger[t.transaction_id]
        assert 0 < float(line.buckets["eoc_credit"]) < float(t.amount), "cash is neither auto-sales nor auto-excluded"
        assert 0.0 < ctx.cash_eligibility[t.transaction_id] < 1.0


def test_ut08_pass_through_retained_economics_only(baseline):
    b = business()
    for m in range(2, 12):
        d = date(2025, m, 20)
        b.credit(d, 100000, f"NEFT/N{b.rrn()}/MEHTA COMMODITIES/HDFC0009876", "NEFT",
                 "Fund Transfer from MEHTA COMMODITIES")
        b.debit(d + timedelta(days=1), 95000, f"NEFT/N{b.rrn()}/ARORA EXPORTS/SBIN0001111", "NEFT",
                "Fund Transfer to ARORA EXPORTS")
    ctx = run(b.build())
    added_eoc = total(ctx, "eoc") - total(baseline, "eoc")
    gross_in = 100000 * 10
    assert any(e.edge_type == PairEdgeType.PASS_THROUGH for e in ctx.pair_graph.edges)
    assert added_eoc < 0.25 * gross_in, f"pass-through added {added_eoc:,.0f} of {gross_in:,.0f} to EOC"


def test_ut09_one_off_capex_does_not_depress_core_opex():
    funded = Decimal("1200000")
    baseline = run(business(opening_balance=funded).build())
    b = business(opening_balance=funded)
    b.debit(date(2025, 9, 9), 850000, f"RTGS/R{b.rrn()}/TATA MOTORS VEHICLE PURCHASE", "RTGS",
            "Fund Transfer to TATA MOTORS")
    ctx = run(b.build())
    assert total(ctx, "capex") >= 850000 * 0.7
    assert total(ctx, "cor") - total(baseline, "cor") < 850000 * 0.2
    # "not permanently": the robust sustainable estimate is essentially unaffected by the one-off month
    assert ctx.sbci.sbci_monthly >= baseline.sbci.sbci_monthly * Decimal("0.95")


def _cycle_ctx(final_purchase_factor: float):
    b = StatementBuilder(months=12, seed=5).lagged_cycle_business(final_purchase_factor=final_purchase_factor)
    return run(b.build())


def test_ut10_purchase_surge_identified_as_build_up():
    ctx = _cycle_ctx(final_purchase_factor=2.5)
    assert ctx.cycle.status == CycleStatus.IDENTIFIED
    # collections arrive Mon-Sat three weeks after purchase; weekly buckets may straddle that span
    assert ctx.cycle.features["WC01_PeakOutflowToInflowLag"] in (21.0, 28.0)
    assert (ctx.cycle.features["WC06_BuildScore"] or 0) > 0
    assert ctx.cycle.build_normalisation_amount > 0
    assert ctx.caocg.basis.value >= ctx.roc.basis.value


def test_ut11_suppressed_purchases_trigger_liquidation_evidence():
    ctx = _cycle_ctx(final_purchase_factor=0.1)
    assert ctx.cycle.status == CycleStatus.IDENTIFIED
    assert (ctx.cycle.features["WC07_LiquidationScore"] or 0) > 0
    assert ctx.cycle.liquidation_normalisation_amount > 0
    assert ctx.caocg.basis.value <= ctx.roc.basis.value


def test_cycle_returns_weak_when_no_lag_evidence():
    b = StatementBuilder(months=4, seed=3)
    for d in b.days():
        b.upi_receipt(d, 800 + (d.toordinal() * 37) % 900)
    b.debit(b.start + timedelta(days=40), 30000, f"NEFT/N{b.rrn()}/SHARMA TRADERS/HDFC0001234", "NEFT",
            "Fund Transfer to SHARMA TRADERS")
    ctx = run(b.build())
    assert ctx.cycle.status == CycleStatus.WEAK_OR_UNIDENTIFIED
    assert ctx.cycle.build_normalisation_amount == 0 and ctx.cycle.liquidation_normalisation_amount == 0


def test_ut12_company_sbci_not_returned_as_director_income():
    ctx = run(business(legal_owner_type=LegalOwnerType.COMPANY).build(), legal=LegalOwnerType.COMPANY)
    assert ctx.sbci.sbci_monthly > 0
    assert ctx.legal.status == LegalAttributionStatus.NEEDS_LEGAL_ATTRIBUTION
    assert ctx.legal.borrower_income_monthly is None
    assert ctx.decision.status == AnalysisStatus.REFER_LEGAL_ATTRIBUTION
    assert ctx.decision.underwriting_income_monthly is None

    docs = {"verified_director_salary_monthly": "60000"}
    ctx = run(business(legal_owner_type=LegalOwnerType.COMPANY).build(), legal=LegalOwnerType.COMPANY, documents=docs)
    assert ctx.legal.status == LegalAttributionStatus.DOCUMENTED_COMPONENTS_ONLY
    assert ctx.legal.borrower_income_monthly == Decimal("60000")


def test_ut13_short_history_reduces_confidence_and_triggers_policy(baseline):
    short = run(business(months=4).build())
    assert short.uncertainty.dimensions["CF02_HistorySufficiency"] < baseline.uncertainty.dimensions["CF02_HistorySufficiency"]
    assert short.uncertainty.confidence < baseline.uncertainty.confidence

    too_short = run(business(months=2).build())
    assert too_short.dq.hard_stop
    assert too_short.dq.status == AnalysisStatus.INSUFFICIENT_HISTORY


_NAME_IN_UPI = re.compile(r"(?<=/CR/)[A-Z ]+(?=/)|(?<=/DR/)[A-Z .]+(?=/)")
_NAME_IN_NEFT = re.compile(r"(?<=/N\d{12}/)[A-Z ]+(?=/)")


def strip_names(builder: StatementBuilder, fraction: float = 1.0, seed: int = 99):
    """Mask counterparty/name-like tokens while preserving dates, amounts, balances and channel/reference
    structure (Section 27.4)."""
    import random
    rng = random.Random(seed)
    for row in builder.rows:
        if row.narration and rng.random() < fraction:
            n = _NAME_IN_UPI.sub("XXXX", row.narration)
            n = _NAME_IN_NEFT.sub("XXXX", n)
            n = re.sub(r"[A-Za-z0-9.]+@", "XXXX@", n)
            row.narration = n
    return builder


def test_ut14_classification_functional_without_counterparty_names(baseline):
    ctx = run(strip_names(business()).build())
    assert ctx.sbci.sbci_monthly > 0
    rel = abs(float(ctx.sbci.sbci_monthly) - float(baseline.sbci.sbci_monthly)) / float(baseline.sbci.sbci_monthly)
    assert rel < 0.5
    bank_fee = [t for t in ctx.txns if "SMS CHGS" in (t.raw_narration or "")]
    assert all(ctx.predictions[t.transaction_id].final_probabilities["D18"] == 1.0 for t in bank_fee)


def test_ut15_aliases_resolve_and_entity_failure_does_not_change_channel_rules(monkeypatch):
    b = business(months=4)
    for m, alias in zip(range(1, 5), ["RAMESH KUMAR", "RAMESH KR", "R KUMAR", "RAMESH KUMAR"]):
        b.credit(date(2025, m, 8), 7000, f"UPI/{b.rrn()}/CR/{alias}/SBIN/rameshk@oksbi", "UPI", f"Fund Transfer from {alias}")
    ctx = run(b.build())
    alias_ids = [t.transaction_id for t in ctx.txns if "RAMESHK@OKSBI" in (t.normalized_narration or "")]
    assert len({ctx.hypotheses[i].cluster_id for i in alias_ids}) == 1, "VPA-linked aliases must share an entity"

    import se_income_engine.pipeline.analyse as pipeline
    from se_income_engine.contracts.entity import EntityHypothesis
    from se_income_engine.contracts.enums import IdentityStatus

    def failed_resolution(txns, identifiers):
        return {t.transaction_id: EntityHypothesis(f"E-{t.transaction_id}", IdentityStatus.UNRESOLVED, None, 0.0)
                for t in txns}

    monkeypatch.setattr(pipeline, "optional_latent_entity_clustering", failed_resolution)
    degraded = run(b.build())
    deterministic = [t for t in ctx.txns if any(r.action == "SET" for r in ctx.predictions[t.transaction_id].rule_adjustments)]
    assert deterministic
    by_id = {t.transaction_id: t for t in degraded.txns}
    for t in deterministic:
        assert degraded.predictions[t.transaction_id].final_probabilities == pytest.approx(
            ctx.predictions[t.transaction_id].final_probabilities)
        assert by_id[t.transaction_id].channel_family == t.channel_family


@pytest.mark.parametrize("narration, bank, names", [
    ("MPAY/UPI/TRTR/111122223333/SHREEGENERAL/HDFC/XXX", "HDFC", ("SHREEGENERAL",)),
    ("MPAY/IMPSI/TRTR/444455556666/CITI/XX123456/", "CITI", ()),
    ("UPIAB/777788889999/CR/AMIT /PUNB/9000000001@NAV", "PUNB", ("AMIT",)),
    ("CRTR/000000001234/09-03-2025 18:02:08/EFT", None, ()),
])
def test_bank_format_codes_are_not_counterparty_bank_or_name(narration, bank, names):
    """Bank transaction-type codes (TRTR, IMPSI, CRTR, EFT) carry no counterparty identity, so they must not
    become the counterparty bank or a name token that links unrelated transactions into one entity."""
    from se_income_engine.contracts.account import Transaction
    from se_income_engine.contracts.enums import Direction
    from se_income_engine.services.m2_role_classifier.s05_identifier_extraction import extract_identifiers

    ids = extract_identifiers(Transaction("T1", "A1", date(2025, 3, 9), Direction.CREDIT, Decimal("100"),
                                          normalized_narration=narration))
    assert ids.bank_code == bank
    assert ids.name_tokens == names


@pytest.mark.parametrize("payment_mode, category", [
    ("Fund Transfer to MADAN NARAYAN", "FUND TRANSFER"),
    ("Fund Transfer from SHREE GENERAL STORE", "FUND TRANSFER"),
    ("Fund Transfer in ", "FUND TRANSFER"),
    ("  bank   charges ", "BANK CHARGES"),
    ("Statutory Payment-Tax", "STATUTORY PAYMENT-TAX"),
    ("", None),
    (None, None),
])
def test_payment_mode_category_drops_the_counterparty(payment_mode, category):
    from se_income_engine.services.m1_parser_normaliser.s03_channel_family_normaliser import payment_mode_category

    assert payment_mode_category(payment_mode) == category


@pytest.mark.parametrize("mode, payment_mode, narration, channel", [
    ("UPI", "Fund Transfer to MADAN NARAYAN", "UPI/DR/123/MADAN", "UPI"),
    ("IMPS", "Penny Drop", "MPAY/IMPSI/TRTR/444455556666", "IMPS"),
    ("Cash-CMS", "Cash Withdrawal", "AEPS CW 0042", "CASH"),
    ("Cash-Bank Branch", "Cash Deposit", "BY CASH", "CASH"),
    ("NACH", "EMI", "ACH/BAJAJ FINANCE", "ACH_NACH"),
    ("UPI", "Bank Charges", "UPI CHARGES", "UPI"),
    ("Other", "Bank Charges", "SMS CHGS QTR", "FEE_CHARGE"),
    ("Other", "Statutory Payment-Tax", "CGST ON SMS CHARGES", "FEE_CHARGE"),
    ("Other", "Interest Received", "SB INT PD", "INTEREST"),
    ("Other", "Fund Transfer to MSEDCL", "NEFT/N123/MSEDCL", "OTHER"),
    (None, None, "NEFT/N123/SHARMA TRADERS/ATM WDL/INT PD", "UNKNOWN"),
])
def test_channel_family_comes_from_source_columns_not_narration(mode, payment_mode, narration, channel):
    from se_income_engine.contracts.account import Transaction
    from se_income_engine.contracts.enums import Direction
    from se_income_engine.services.m1_parser_normaliser.s03_channel_family_normaliser import normalize_channel

    fields = {k: v for k, v in (("Mode", mode), ("Payment Mode", payment_mode)) if v is not None}
    txn = Transaction("T1", "A1", date(2025, 3, 9), Direction.DEBIT, Decimal("100"), raw_narration=narration,
                      normalized_narration=narration, parser_fields=fields)
    assert normalize_channel(txn).value == channel
