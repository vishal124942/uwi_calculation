"""Section 7.4 - Rule/model interaction (M3 Rule overlay).

Deterministic overrides only where semantics are strong (confidence >= rule_override_confidence);
otherwise rules re-weight probabilities. Every adjustment is logged on the RolePrediction.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from se_income_engine.common.stats import normalise, normalised_entropy
from se_income_engine.config.parameters import RoleParameters
from se_income_engine.contracts.account import Transaction
from se_income_engine.contracts.enums import ChannelFamily
from se_income_engine.contracts.role import RolePrediction, RuleAdjustment
from se_income_engine.services.step03_transaction_evidence.s05_identifier_extraction import TransactionIdentifiers
from se_income_engine.services.step03_transaction_evidence.s08_neighbourhood_features import NeighbourhoodFeatures
from se_income_engine.versions import COMPONENT_VERSIONS

_LOAN_DISB = re.compile(r"LOAN\s*(A/?C\s*)?DISB|DISBURSAL|DISBURSEMENT")
_STRONG_CHARGE = re.compile(r"CHGS?|CHARGES|MIN_BAL|MIN BAL|SMS|AMC|CGST|SGST|GENERAL CHARGES")
_EMI = re.compile(r"\bEMI\b")
_LOAN_WORD = re.compile(r"\b(LOAN|EMI|FINANCE|FINSERV|BAJAJ)\b")
_STATUTORY = re.compile(r"\b(GST|GSTN|TDS|CHALLAN|CBDT|EPFO|ESIC|ADVANCE TAX|OLTAS)\b")
_REVERSAL = re.compile(r"\b(REVERSAL|REVERSED|REFUND)\b")


@dataclass
class RuleContext:
    txn: Transaction
    ids: TransactionIdentifiers
    nf: NeighbourhoodFeatures
    hint: str
    text: str


@dataclass(frozen=True)
class OverlayRule:
    rule_id: str
    description: str
    applies: Callable[[RuleContext], bool]
    confidence: float
    action: str  # SET | MULTIPLY | RESTRICT
    roles: Callable[[RuleContext, RoleParameters], dict[str, float]]


def _rules() -> list[OverlayRule]:
    return [
        OverlayRule("R001_LOAN_DISBURSEMENT", "Explicit loan disbursement marker",
                    lambda c: c.txn.is_credit and (c.hint == "LOAN DISBURSAL" or bool(_LOAN_DISB.search(c.text))),
                    0.996, "SET", lambda c, p: {"C05": 1.0}),
        OverlayRule("R002_BANK_CHARGE", "Bank fee/charge with explicit charge marker",
                    lambda c: not c.txn.is_credit and c.txn.channel_family == ChannelFamily.FEE_CHARGE and
                    (c.hint in ("BANK CHARGES", "MINIMUM BALANCE CHARGES") or bool(_STRONG_CHARGE.search(c.text))),
                    0.997, "SET", lambda c, p: {"D18": 1.0}),
        OverlayRule("R003_INTEREST_CREDIT", "Bank interest credit",
                    lambda c: c.txn.is_credit and (c.txn.channel_family == ChannelFamily.INTEREST or
                                                   c.hint == "INTEREST RECEIVED"),
                    0.996, "SET", lambda c, p: {"C10": 1.0}),
        OverlayRule("R004_EMI_DEBIT", "EMI / loan mandate debit split by configured interest share (UT-05)",
                    lambda c: not c.txn.is_credit and (c.hint == "EMI" or bool(_EMI.search(c.text)) or
                                                       (c.txn.channel_family == ChannelFamily.ACH_NACH and
                                                        bool(_LOAN_WORD.search(c.text)))),
                    0.995, "SET", lambda c, p: {"D09": 1 - p.emi_interest_share, "D08": p.emi_interest_share}),
        OverlayRule("R005_RAPID_RECIPROCAL_FLOW", "Rapid reciprocal flow above theta_recycle (Section 7.4)",
                    lambda c: max(c.nf.NF11_ReciprocalClusterScore, c.nf.NF12_FlowRecyclingScore) > 0.0,
                    0.9, "MULTIPLY", None),  # roles resolved in apply()
        OverlayRule("R006_EXPLICIT_REVERSAL", "Explicit reversal/refund marker",
                    lambda c: c.hint == "REVERSAL" or bool(_REVERSAL.search(c.text)),
                    0.98, "MULTIPLY", lambda c, p: {"C08": 20.0} if c.txn.is_credit else {"D15": 20.0}),
        OverlayRule("R007_STATUTORY_PAYMENT", "Statutory challan/GST/TDS outflow",
                    lambda c: not c.txn.is_credit and c.txn.channel_family != ChannelFamily.FEE_CHARGE and
                    (c.hint == "STATUTORY PAYMENT-TAX" or bool(_STATUTORY.search(c.text))),
                    0.98, "MULTIPLY", lambda c, p: {"D07": 20.0}),
        OverlayRule("R008_GAMBLING", "Gambling/betting outflow is personal",
                    lambda c: not c.txn.is_credit and c.hint == "GAMBLING",
                    0.995, "SET", lambda c, p: {"D13": 1.0}),
        OverlayRule("R009_CASH_DEPOSIT_SCOPE", "Cash deposits restricted to cash-compatible roles",
                    lambda c: c.txn.is_credit and c.txn.channel_family == ChannelFamily.CASH,
                    0.99, "RESTRICT", lambda c, p: {"C03": 1, "C04": 1, "C06": 1, "C11": 1, "C13": 1}),
        OverlayRule("R010_CASH_WITHDRAWAL_SCOPE", "Cash withdrawals restricted to cash-compatible roles",
                    lambda c: not c.txn.is_credit and c.txn.channel_family in (ChannelFamily.CASH, ChannelFamily.ATM),
                    0.99, "RESTRICT", lambda c, p: {"D16": 1, "D12": 1, "D13": 1, "D19": 1}),
        OverlayRule("R011_PENNY_DROP", "Account-verification penny drop is non-economic",
                    lambda c: c.hint == "PENNY DROP",
                    0.995, "SET", lambda c, p: {"C13": 1.0} if c.txn.is_credit else {"D18": 1.0}),
        OverlayRule("R012_INTERNAL_BOOK", "Bank book transfer / sweep marker",
                    lambda c: c.txn.channel_family == ChannelFamily.INTERNAL_BOOK,
                    0.97, "MULTIPLY", lambda c, p: {"C04": 10.0} if c.txn.is_credit else {"D14": 10.0}),
    ]


RULES = _rules()


def refresh_prediction(pred: RolePrediction) -> None:
    pred.final_probabilities = normalise(pred.final_probabilities)
    pred.top_role = max(pred.final_probabilities, key=pred.final_probabilities.get)
    pred.top_probability = pred.final_probabilities[pred.top_role]
    pred.entropy = normalised_entropy(pred.final_probabilities)


def _apply_rule(rule: OverlayRule, ctx: RuleContext, pred: RolePrediction, p: RoleParameters, version: str) -> None:
    probs = dict(pred.final_probabilities)
    if rule.rule_id == "R005_RAPID_RECIPROCAL_FLOW":
        score = max(ctx.nf.NF11_ReciprocalClusterScore, ctx.nf.NF12_FlowRecyclingScore)
        if score <= p.theta_recycle:
            return
        roles = {"C04": p.alpha_transfer, "C01": p.beta_operating} if ctx.txn.is_credit else \
            {"D14": p.alpha_transfer, "D01": p.beta_operating}
        for r, f in roles.items():
            probs[r] = probs.get(r, 0.0) * f
        pred.final_probabilities = normalise(probs)
        pred.rule_adjustments.append(RuleAdjustment(rule.rule_id, version, "MULTIPLY", roles,
                                                    f"{rule.description}; score={score:.3f}"))
        return

    roles = rule.roles(ctx, p)
    action = rule.action
    if action == "SET" and rule.confidence < p.rule_override_confidence:
        action = "MULTIPLY"
        roles = {r: 20.0 for r in roles}
    if action == "SET":
        probs = {r: roles.get(r, 0.0) for r in probs}
    elif action == "MULTIPLY":
        for r, f in roles.items():
            probs[r] = max(probs.get(r, 0.0), 1e-6) * f
    elif action == "RESTRICT":
        probs = {r: (v if r in roles else 0.0) for r, v in probs.items()}
        if sum(probs.values()) == 0:
            probs = {r: (1.0 if r in roles else 0.0) for r in probs}
    pred.final_probabilities = normalise(probs)
    pred.rule_adjustments.append(RuleAdjustment(rule.rule_id, version, action, roles, rule.description))


def apply_versioned_rule_overlay(
    predictions: dict[str, RolePrediction],
    txns: list[Transaction],
    identifiers: dict[str, TransactionIdentifiers],
    features: dict[str, NeighbourhoodFeatures],
    p: RoleParameters,
) -> dict[str, RolePrediction]:
    version = COMPONENT_VERSIONS["rule_overlay"]
    for t in txns:
        pred = predictions[t.transaction_id]
        ctx = RuleContext(t, identifiers[t.transaction_id], features[t.transaction_id],
                          (t.parser_fields.get("Payment Mode") or "").strip().upper(), t.normalized_narration or "")
        set_applied = False
        for rule in RULES:
            if set_applied and rule.action != "SET":
                continue
            if rule.applies(ctx):
                _apply_rule(rule, ctx, pred, p, version)
                if rule.action == "SET" and rule.confidence >= p.rule_override_confidence:
                    set_applied = True
        refresh_prediction(pred)
    return predictions
