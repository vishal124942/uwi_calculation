"""Section 7 - Probabilistic economic-role inference (M2 Role classifier).

Baseline model: a log-linear evidence model over the Section 7.2 evidence hierarchy
(channel markers, structured identifiers, narration text, recurrence, neighbourhood).
logit(role) = ln(prior(role)) + sum(evidence log-likelihood ratios); probabilities = softmax.

It exposes ``predict`` so a trained gradient-boosted / transformer ensemble can replace it without
changing any downstream service. Missing narration never breaks prediction (UT-02, UT-14).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from se_income_engine.common.stats import quantile, softmax
from se_income_engine.contracts.account import Transaction
from se_income_engine.contracts.entity import EntityHypothesis
from se_income_engine.contracts.enums import ChannelFamily, IdentityStatus
from se_income_engine.contracts.role import RolePrediction
from se_income_engine.services.m2_role_classifier.s05_entity_resolution import ClusterStatistics
from se_income_engine.services.m2_role_classifier.s05_identifier_extraction import TransactionIdentifiers
from se_income_engine.services.m2_role_classifier.s08_neighbourhood_features import NeighbourhoodFeatures
from se_income_engine.versions import COMPONENT_VERSIONS

CREDIT_PRIORS = {
    "C01": 0.45, "C02": 0.04, "C03": 0.05, "C04": 0.08, "C05": 0.03, "C06": 0.02, "C07": 0.02,
    "C08": 0.02, "C09": 0.005, "C10": 0.01, "C11": 0.08, "C12": 0.03, "C13": 0.165,
}
DEBIT_PRIORS = {
    "D01": 0.2, "D02": 0.05, "D03": 0.03, "D04": 0.04, "D05": 0.03, "D06": 0.1, "D07": 0.02, "D08": 0.01,
    "D09": 0.03, "D10": 0.01, "D11": 0.01, "D12": 0.08, "D13": 0.12, "D14": 0.06, "D15": 0.01, "D16": 0.03,
    "D17": 0.03, "D18": 0.03, "D19": 0.1,
}


# Roles that are economically implausible without a positive marker (lender, mandate, charge, tax, asset,
# reversal, cash or pairing evidence). Without evidence their prior mass is suppressed instead of leaking
# into every transaction, so e.g. unexplained supplier debits do not create phantom debt service.
EVIDENCE_GATED_CREDIT = ("C03", "C05", "C07", "C08", "C09", "C10", "C12")
EVIDENCE_GATED_DEBIT = ("D07", "D08", "D09", "D10", "D11", "D12", "D13", "D14", "D15", "D16", "D17", "D18")
GATE_PENALTY = 3.0


def _gate_unevidenced(logits: dict[str, float], priors: dict[str, float], gated: tuple[str, ...]) -> dict[str, float]:
    for role in gated:
        if logits[role] <= math.log(priors[role]) + 1e-12:
            logits[role] -= GATE_PENALTY
    return logits


def _rx(words: str) -> re.Pattern:
    return re.compile(rf"\b({words})\b")


CREDIT_LEXICON: list[tuple[str, re.Pattern, float]] = [
    ("C05", _rx(r"LOAN|DISB\w*|FINANCE|FINSERV|FINCORP|CREDIT LINE|KREDITBEE|MONEYVIEW|NAVI|FIBE|LENDINGKART|"
                r"INDIFI|SMALL FINANCE BANK|MICROFIN\w*|NBFC|OD DRAWDOWN|MPOKKET|BELSTAR|MUTHOOT|MANAPPURAM"), 4.0),
    ("C08", _rx(r"REV|REVERSAL|REVERSED|REFUND|RFND|RETURN|RTN|CHARGEBACK|FAILED|DECLINED"), 3.5),
    ("C09", _rx(r"IT REFUND|ITDREFUND|TAX REFUND|CBDT|GST REFUND|INCOME TAX"), 5.0),
    ("C10", _rx(r"DIVIDEND|INT\.?\s?PD|INTEREST"), 3.0),
    ("C07", _rx(r"REDEMPTION|REDEEM|MUTUAL FUND|FD CLOS\w*|FD MAT\w*|MATURITY|ZERODHA|GROWW|UPSTOX|SECURITIES|"
                r"SALE PROCEEDS|CHITS?|CHIT FUNDS?"), 4.0),
    ("C04", _rx(r"SELF|OWN A/?C|SWEEP|OWN ACCOUNT"), 3.0),
    ("C06", _rx(r"CAPITAL INTRO\w*|PROMOTER|SHARE CAPITAL|OWNER CAPITAL"), 4.0),
    ("C11", _rx(r"GIFT|FAMILY|SALARY|SAL CR|PENSION|HOUSEHOLD|POCKET MONEY"), 2.5),
    ("C02", _rx(r"PAYTM|PHONEPE|BHARATPE|GPAY|GOOGLE PAY|AMAZON|FLIPKART|SWIGGY|ZOMATO|MEESHO|POS SETT\w*|SETTLEMENT"), 2.0),
]

DEBIT_LEXICON: list[tuple[str, re.Pattern, float]] = [
    ("D07", _rx(r"GST|GSTN|CBDT|TDS|ADVANCE TAX|INCOME TAX|CHALLAN|EPFO|ESIC|PROFESSION TAX|PTAX|TIN NSDL|OLTAS"), 4.5),
    ("D08", _rx(r"INT ON LOAN|LOAN INT|OD INT|INTEREST DEBIT|INT\.? DR"), 4.0),
    ("D02", _rx(r"SALARY|SAL|WAGES?|PAYROLL|LABOUR|LABOR|STAFF|BONUS"), 3.5),
    ("D03", _rx(r"RENT|LEASE|LANDLORD"), 4.0),
    ("D04", _rx(r"ELECTRICITY|MSEDCL|BESCOM|TATA POWER|ADANI ELEC\w*|TORRENT|BSES|AIRTEL|JIO|VODAFONE|BSNL|"
                r"BROADBAND|RECHARGE|WATER|POSTPAID|PREPAID|DTH|TATA PLAY|FIBERNET"), 3.5),
    ("D05", _rx(r"TRANSPORT|LOGISTICS|COURIER|FREIGHT|DELHIVERY|BLUEDART|DTDC|PORTER|ECOM EXPRESS|SHADOWFAX|CARGO|"
                r"TRUCK|ROADWAYS|PETROL|DIESEL|FUEL|HPCL|BPCL|IOCL|INDIAN OIL|FASTAG"), 3.0),
    ("D01", _rx(r"TRADERS?|TRADING|ENTERPRISES?|AGENC(?:Y|IES)|DISTRIBUTORS?|WHOLESALE|SUPPLIERS?|SUPPLY|INDUSTRIES|"
                r"AGRO|MILLS?|STORES?|PROVISIONS?|MART|GENERAL|KIRANA|PHARMA|MEDICALS?|HARDWARE|TEXTILES?|"
                r"GARMENTS?|STEEL|CEMENT|ELECTRICALS?|CORPORATION|IMPEX|EXPORTS?|IMPORTS?|SALES"), 2.2),
    ("D06", _rx(r"SERVICES?|SOLUTIONS|TECHNOLOGIES|SOFTWARE|ADVERTIS\w*|MARKETING|PRINTING|STATIONERY|CONSULT\w*|"
                r"PROFESSIONAL|LEGAL|AUDIT|ACCOUNTANT|GOOGLE ADS|FACEBOOK|AWS|ZOHO|TALLY"), 2.5),
    ("D10", _rx(r"MACHINE\w*|EQUIPMENT|VEHICLE|MOTORS?|AUTOMOBILES?|MARUTI|TATA MOTORS|MAHINDRA|FURNITURE|LAPTOP|"
                r"COMPUTER|GENERATOR|TRACTOR"), 4.5),
    ("D11", _rx(r"REPAIR\w*|SERVICE CENT\w*|SPARES?|SPARE PARTS|MAINTENANCE"), 3.0),
    ("D12", _rx(r"SELF|CHITS?|CHIT FUNDS?|RD INSTAL\w*|RECURRING DEPOSIT|SIP|MUTUAL FUND|PPF"), 3.5),
    ("D13", _rx(r"DREAM11|RUMMY|MPL|POKER|BET\w*|CASINO|LOTTERY|GAMBL\w*|NETFLIX|HOTSTAR|SPOTIFY|BOOKMYSHOW|MOVIE|"
                r"ZOMATO|SWIGGY|DOMINOS|PIZZA|RESTAURANT|SCHOOL|COLLEGE|TUITION|HOSPITAL|CLINIC|INSURANCE|LIC|"
                r"PREMIUM|JEWELL\w*|SALON|MYNTRA|AJIO|NYKAA"), 2.5),
    ("D14", _rx(r"SWEEP|OWN A/?C|TRF TO SELF|OWN ACCOUNT"), 3.0),
    ("D15", _rx(r"REV|REVERSAL|REFUND|RETURN|RTN|CHARGEBACK"), 3.5),
]

_DEBT_SERVICE = _rx(r"EMI|LOAN|REPAY\w*|INSTAL\w*|BAJAJ FIN\w*")

_PARSER_HINTS_CREDIT = {
    "LOAN DISBURSAL": ("C05", 5.0), "REVERSAL": ("C08", 4.0), "INTEREST RECEIVED": ("C10", 5.0),
    "CASH DEPOSIT": ("C03", 5.0), "INVESTMENT": ("C07", 3.0), "PENNY DROP": ("C13", 4.0),
}
_PARSER_HINTS_DEBIT = {
    "BANK CHARGES": ("D18", 5.0), "MINIMUM BALANCE CHARGES": ("D18", 5.0), "STATUTORY PAYMENT-TAX": ("D07", 4.0),
    "GAMBLING": ("D13", 6.0), "TELEPHONE": ("D04", 3.5), "PETROL": ("D05", 3.0), "INSURANCE": ("D13", 3.0),
    "CASH WITHDRAWAL": ("D16", 4.0), "REVERSAL": ("D15", 4.0), "INVESTMENT": ("D13", 1.5),
}

_THIRD_PARTY_RAILS = {ChannelFamily.UPI, ChannelFamily.IMPS, ChannelFamily.NEFT, ChannelFamily.RTGS,
                      ChannelFamily.CHEQUE, ChannelFamily.CMS, ChannelFamily.POS_CARD}


@dataclass
class AccountRoleContext:
    """Account-level statistics consumed by the classifier (Layer 4/6 context)."""

    amount_p50: float
    amount_p90: float
    amount_p99: float
    payers_per_month: float  # distinct resolved payer clusters per active month


def build_account_contexts(txns: list[Transaction], hypotheses: dict[str, EntityHypothesis]) -> dict[str, AccountRoleContext]:
    by_account: dict[str, list[Transaction]] = {}
    for t in txns:
        by_account.setdefault(t.account_id, []).append(t)
    out = {}
    for aid, items in by_account.items():
        amounts = [float(t.amount) for t in items]
        credits = [t for t in items if t.is_credit]
        payers_by_month: dict[str, set[str]] = {}
        for t in credits:
            hyp = hypotheses[t.transaction_id]
            if hyp.identity_status != IdentityStatus.UNRESOLVED:
                payers_by_month.setdefault(t.booking_date.strftime("%Y-%m"), set()).add(hyp.cluster_id)
        months = {t.booking_date.strftime("%Y-%m") for t in credits}
        out[aid] = AccountRoleContext(
            amount_p50=quantile(amounts, 0.5) or 0.0,
            amount_p90=quantile(amounts, 0.9) or 0.0,
            amount_p99=quantile(amounts, 0.99) or 0.0,
            payers_per_month=sum(len(s) for s in payers_by_month.values()) / len(months) if months else 0.0,
        )
    return out


def _identified_third_party(ids: TransactionIdentifiers) -> bool:
    """Resolved counterparty identity that is not the account holder (VPA / name / merchant / mandate)."""
    if ids.own_account_marker or ids.holder_name_match > 0.0:
        return False
    return bool(ids.vpa_local or ids.name_tokens or ids.merchant_id or ids.mandate_id)


def _is_round(amount: float) -> bool:
    return amount >= 1000 and amount % 500 == 0


def _recurring_fixed(cs: ClusterStatistics | None, debit: bool) -> bool:
    if cs is None:
        return False
    months = cs.debit_months if debit else cs.credit_months
    if len(months) < 3 or len(cs.amounts) < 3:
        return False
    m = sum(cs.amounts) / len(cs.amounts)
    sd = math.sqrt(sum((a - m) ** 2 for a in cs.amounts) / len(cs.amounts))
    return m > 0 and sd / m < 0.2


class RoleClassifier:
    model_version = COMPONENT_VERSIONS["role_model"]

    def __init__(self, emi_interest_share: float = 0.35):
        self.emi_interest_share = emi_interest_share

    def _credit_logits(self, t, ids, hyp, cs, nf, ctx) -> dict[str, float]:
        logits = {r: math.log(p) for r, p in CREDIT_PRIORS.items()}
        text = t.normalized_narration or ""
        hint = t.payment_mode or ""
        cpt = (t.parser_fields.get("Counter Party Type") or "").strip().upper()
        amt = float(t.amount)

        # Layer 1: explicit bank/channel markers
        ch = t.channel_family
        if ch == ChannelFamily.INTEREST:
            logits["C10"] += 5.0
        elif ch == ChannelFamily.CASH:
            logits["C03"] += 5.0
        elif ch == ChannelFamily.MERCHANT_SETTLEMENT:
            logits["C02"] += 4.5
        elif ch == ChannelFamily.INTERNAL_BOOK:
            logits["C04"] += 4.0
        elif ch == ChannelFamily.FEE_CHARGE:
            logits["C08"] += 3.0
        if hint in _PARSER_HINTS_CREDIT:
            role, w = _PARSER_HINTS_CREDIT[hint]
            logits[role] += w
        if "SETTLEMENT" in (t.parser_fields.get("Sub Payment Mode") or "").upper():
            logits["C02"] += 4.0
        if cpt == "NBFC":
            logits["C05"] += 2.5
        if cpt == "PAYMENT_GATEWAY":
            logits["C02"] += 3.0

        # Layer 2: structured identifiers
        if ids.own_account_marker:
            logits["C04"] += 3.0
        if ids.holder_name_match >= 0.99:
            strong = len(ids.name_tokens) >= 2
            logits["C04"] += 2.5 if strong else 1.0
            logits["C06"] += 1.0 if strong else 0.3
            if strong:
                logits["C01"] -= 1.5
        if _identified_third_party(ids):
            logits["C13"] -= 1.5
            logits["C04"] -= 1.5

        # Layer 3: narration text
        for role, pattern, w in CREDIT_LEXICON:
            if text and pattern.search(text):
                logits[role] += w

        # Layer 4: recurrence and ticket structure
        if ch in _THIRD_PARTY_RAILS and not ids.own_account_marker:
            logits["C01"] += 0.8
            if cpt in ("PER", "ORG"):
                logits["C01"] += 0.3
            if amt <= ctx.amount_p90:
                logits["C01"] += 0.4
            if ctx.payers_per_month >= 50:
                logits["C01"] += 1.0
            elif ctx.payers_per_month >= 15:
                logits["C01"] += 0.5
        if cs and hyp.identity_status != IdentityStatus.UNRESOLVED and len(cs.credit_months) >= 2 and cs.debit_count == 0:
            logits["C01"] += 0.6
        if _is_round(amt) and cpt == "PER" and amt >= ctx.amount_p99:
            logits["C11"] += 0.7
            logits["C06"] += 0.3
        one_off = cs is None or len(cs.amounts) <= 1
        if one_off and amt >= max(ctx.amount_p99, 20.0 * ctx.amount_p50):
            logits["C01"] -= 0.6
            for role in ("C05", "C06", "C07", "C11"):
                logits[role] += 0.4

        # Layer 5: neighbourhood
        if nf.NF07_BalanceRetention3d is not None and nf.NF07_BalanceRetention3d < 0.1 and nf.NF03_AmountMatchedOut24h >= 0.95 \
                and amt >= max(500.0, ctx.amount_p90):
            logits["C12"] += 1.0
        if not text and ch == ChannelFamily.UNKNOWN:
            logits["C13"] += 1.0
        return _gate_unevidenced(logits, CREDIT_PRIORS, EVIDENCE_GATED_CREDIT)

    def _debit_logits(self, t, ids, hyp, cs, nf, ctx) -> dict[str, float]:
        logits = {r: math.log(p) for r, p in DEBIT_PRIORS.items()}
        text = t.normalized_narration or ""
        hint = t.payment_mode or ""
        cpt = (t.parser_fields.get("Counter Party Type") or "").strip().upper()
        amt = float(t.amount)
        s = self.emi_interest_share

        ch = t.channel_family
        debt_w = 0.0
        if ch == ChannelFamily.FEE_CHARGE:
            logits["D18"] += 5.0
        elif ch in (ChannelFamily.ATM, ChannelFamily.CASH):
            logits["D16"] += 4.5
            logits["D12"] += 3.5
            logits["D13"] += 1.5
        elif ch == ChannelFamily.INTERNAL_BOOK:
            logits["D14"] += 4.0
        elif ch == ChannelFamily.ACH_NACH:
            debt_w += 2.5
        if hint == "EMI":
            debt_w += 5.0
        elif hint in _PARSER_HINTS_DEBIT:
            role, w = _PARSER_HINTS_DEBIT[hint]
            logits[role] += w
        if cpt == "NBFC":
            debt_w += 2.5
        if cpt == "PAYMENT_GATEWAY":
            logits["D13"] += 1.0
            logits["D06"] += 0.5
        if cpt == "PER":
            logits["D02"] += 0.3
            logits["D13"] += 0.4
            logits["D01"] += 0.2
            logits["D17"] += 0.2
        if cpt == "ORG":
            logits["D01"] += 0.8
            logits["D06"] += 0.5

        if ids.own_account_marker:
            logits["D14"] += 2.5
            logits["D12"] += 2.0
        if ids.holder_name_match >= 0.99:
            strong = len(ids.name_tokens) >= 2
            logits["D12"] += 2.0 if strong else 0.7
            logits["D14"] += 1.5 if strong else 0.5
            if strong:
                for role in ("D01", "D02", "D03", "D04", "D05", "D06"):
                    logits[role] -= 2.0
        if _identified_third_party(ids):
            logits["D19"] -= 1.5
            logits["D14"] -= 1.5

        for role, pattern, w in DEBIT_LEXICON:
            if text and pattern.search(text):
                logits[role] += w
        if text and _DEBT_SERVICE.search(text):
            debt_w += 3.0

        if debt_w:
            logits["D09"] += debt_w + math.log(1 - s) - math.log(DEBIT_PRIORS["D09"] / (DEBIT_PRIORS["D09"] + DEBIT_PRIORS["D08"]))
            logits["D08"] += debt_w + math.log(s) - math.log(DEBIT_PRIORS["D08"] / (DEBIT_PRIORS["D09"] + DEBIT_PRIORS["D08"]))

        if _recurring_fixed(cs, debit=True) and hyp.identity_status != IdentityStatus.UNRESOLVED:
            for role in ("D02", "D03", "D04"):
                logits[role] += 0.8
        org_like = cpt == "ORG" or any(p.search(text) for r, p, _ in DEBIT_LEXICON if r in ("D01", "D06") and text)
        if cs and org_like and len(cs.debit_months) >= 2 and cs.debit_count >= 3:
            logits["D01"] += 0.7
        if amt >= max(50000.0, ctx.amount_p99):
            logits["D10"] += 0.8
            if cs is None or len(cs.amounts) <= 1:
                for role in ("D01", "D02", "D03", "D04", "D05", "D06"):
                    logits[role] -= 0.6

        if (nf.NF05_PriorMatchedIn7d or 0.0) >= 0.95 and amt >= max(500.0, ctx.amount_p90):
            logits["D17"] += 1.0
        if not text and ch == ChannelFamily.UNKNOWN:
            logits["D19"] += 1.0
        return _gate_unevidenced(logits, DEBIT_PRIORS, EVIDENCE_GATED_DEBIT)

    def predict(
        self,
        txns: list[Transaction],
        identifiers: dict[str, TransactionIdentifiers],
        hypotheses: dict[str, EntityHypothesis],
        cluster_stats: dict[str, ClusterStatistics],
        features: dict[str, NeighbourhoodFeatures],
    ) -> dict[str, RolePrediction]:
        contexts = build_account_contexts(txns, hypotheses)
        out: dict[str, RolePrediction] = {}
        for t in txns:
            ids = identifiers[t.transaction_id]
            hyp = hypotheses[t.transaction_id]
            cs = cluster_stats.get(hyp.cluster_id)
            nf = features[t.transaction_id]
            ctx = contexts[t.account_id]
            logits = self._credit_logits(t, ids, hyp, cs, nf, ctx) if t.is_credit else \
                self._debit_logits(t, ids, hyp, cs, nf, ctx)
            probs = softmax(logits)
            out[t.transaction_id] = RolePrediction(t.transaction_id, probs, self.model_version, dict(probs))
        return out
