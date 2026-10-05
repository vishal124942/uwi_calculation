"""Section 17 - Multi-account consolidation and inter-account transfer graph (MA01-MA10)."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from se_income_engine.common.money import ZERO, weighted
from se_income_engine.config.parameters import MultiAccountParameters
from se_income_engine.contracts.account import AccountInput, Transaction
from se_income_engine.contracts.enums import AccountType, ChannelFamily, PairEdgeType
from se_income_engine.contracts.role import RolePrediction, RuleAdjustment
from se_income_engine.services.step03_transaction_evidence.s05_identifier_extraction import TransactionIdentifiers
from se_income_engine.services.step05_pairing_and_multi_account.s08_flow_pair_graph import FlowPairGraph, PairEdge
from se_income_engine.services.step03_transaction_evidence.s08_neighbourhood_features import amount_similarity

_INCOMPATIBLE = {ChannelFamily.FEE_CHARGE, ChannelFamily.INTEREST, ChannelFamily.ATM, ChannelFamily.CASH}


def consolidate_transaction_stream(accounts: list[AccountInput]) -> list[Transaction]:
    txns = [t for a in accounts for t in a.transactions]
    return sorted(txns, key=lambda t: (t.booking_date, t.account_id, t.sequence_no))


def multiple_supplied_accounts(accounts: list[AccountInput]) -> bool:
    return len(accounts) > 1


_BANK_RAILS = {ChannelFamily.NEFT, ChannelFamily.IMPS, ChannelFamily.RTGS, ChannelFamily.INTERNAL_BOOK}
_NEUTRAL_CHANNELS = {ChannelFamily.OTHER, ChannelFamily.UNKNOWN}


def _channels_compatible(a: ChannelFamily, b: ChannelFamily) -> bool:
    if a == b or a in _NEUTRAL_CHANNELS or b in _NEUTRAL_CHANNELS:
        return True
    return a in _BANK_RAILS and b in _BANK_RAILS


def _account_suffix(account: AccountInput) -> str | None:
    digits = "".join(ch for ch in (account.parser_metadata.get("masked_account") or account.account_id) if ch.isdigit())
    return digits[-4:] if len(digits) >= 4 else None


def _ownership_linkage(c: Transaction, d: Transaction, ids: dict[str, TransactionIdentifiers],
                       suffixes: dict[str, str | None]) -> bool | None:
    """True = positive own-account evidence, False = evidence of a third party, None = indeterminate."""
    ci, di = ids.get(c.transaction_id), ids.get(d.transaction_id)
    if ci is None or di is None:
        return None
    if (ci.utr and ci.utr == di.utr) or ci.own_account_marker or di.own_account_marker:
        return True
    if (ci.account_fragment and suffixes.get(d.account_id) and ci.account_fragment.endswith(suffixes[d.account_id])) or \
            (di.account_fragment and suffixes.get(c.account_id) and di.account_fragment.endswith(suffixes[c.account_id])):
        return True
    if ci.holder_name_match >= 0.99 or di.holder_name_match >= 0.99:
        return True
    named_third_party = [x for x in (ci, di) if x.name_tokens and x.holder_name_match == 0.0]
    return False if named_third_party else None


def match_interaccount_transfers(accounts: list[AccountInput], pair_graph: FlowPairGraph,
                                 p: MultiAccountParameters,
                                 identifiers: dict[str, TransactionIdentifiers] | None = None) -> list[PairEdge]:
    """Section 17.2 maximum-weight one-to-one matching (greedy by score) between a debit in one supplied account
    and a credit in another supplied account of the same customer, subject to ownership linkage != false and
    channel/reference compatibility."""
    identifiers = identifiers or {}
    owners = {a.account_id: a.customer_id for a in accounts}
    suffixes = {a.account_id: _account_suffix(a) for a in accounts}
    already = pair_graph.txn_ids(PairEdgeType.REVERSAL)
    credits = [t for a in accounts for t in a.transactions if t.is_credit and t.channel_family not in _INCOMPATIBLE
               and t.transaction_id not in already]
    debits = [t for a in accounts for t in a.transactions if not t.is_credit and t.channel_family not in _INCOMPATIBLE
              and t.transaction_id not in already]
    credits_by_id = {c.transaction_id: c for c in credits}
    credits_by_amount: dict[int, list[Transaction]] = defaultdict(list)
    for c in credits:
        credits_by_amount[int(c.amount)].append(c)

    candidates: list[PairEdge] = []
    for d in debits:
        for bucket in (int(d.amount) - 1, int(d.amount), int(d.amount) + 1):
            for c in credits_by_amount.get(bucket, []):
                if c.account_id == d.account_id or owners[c.account_id] != owners[d.account_id]:
                    continue
                gap = abs((c.booking_date - d.booking_date).days)
                sim = amount_similarity(c.amount, d.amount)
                if gap > p.transfer_max_gap_days or sim < p.transfer_amount_similarity:
                    continue
                if not _channels_compatible(c.channel_family, d.channel_family):
                    continue
                linkage = _ownership_linkage(c, d, identifiers, suffixes)
                if linkage is False:
                    continue
                if linkage is None and float(c.amount) < p.unlinked_min_amount:
                    continue
                score = sim * (1.0 - gap / (p.transfer_max_gap_days + 1)) * (1.0 if linkage else 0.6)
                candidates.append(PairEdge(f"IT-{d.transaction_id[:8]}-{c.transaction_id[:8]}",
                                           PairEdgeType.INTERNAL_TRANSFER, c.transaction_id, d.transaction_id,
                                           score, sim, gap * 24.0,
                                           {"from_account": d.account_id, "to_account": c.account_id,
                                            "ownership_linkage": "POSITIVE" if linkage else "INDETERMINATE"}))
    # Duplicate safeguard: an indeterminate-linkage candidate is kept only if its amount is unique among candidates.
    per_amount: dict[tuple[str, int], int] = defaultdict(int)
    for e in candidates:
        if e.evidence["ownership_linkage"] == "INDETERMINATE":
            per_amount[(e.evidence["from_account"], int(credits_by_id[e.credit_txn_id].amount))] += 1
    candidates = [e for e in candidates if e.evidence["ownership_linkage"] == "POSITIVE" or
                  per_amount[(e.evidence["from_account"], int(credits_by_id[e.credit_txn_id].amount))] == 1]
    used: set[str] = set()
    accepted: list[PairEdge] = []
    for e in sorted(candidates, key=lambda e: (-e.score, e.edge_id)):
        if e.credit_txn_id in used or e.debit_txn_id in used:
            continue
        used.update((e.credit_txn_id, e.debit_txn_id))
        accepted.append(e)
    return accepted


def exclude_internal_transfer_economics(internal_edges: list[PairEdge], predictions: dict[str, RolePrediction],
                                        pair_graph: FlowPairGraph) -> None:
    """Matched supplied-account transfers are deterministic and supersede weaker in-account pair edges."""
    internal_ids = {i for e in internal_edges for i in (e.credit_txn_id, e.debit_txn_id)}
    pair_graph.edges = [e for e in pair_graph.edges
                        if e.credit_txn_id not in internal_ids and e.debit_txn_id not in internal_ids]
    for e in internal_edges:
        cp, dp = predictions[e.credit_txn_id], predictions[e.debit_txn_id]
        cp.final_probabilities = {r: (1.0 if r == "C04" else 0.0) for r in cp.final_probabilities}
        dp.final_probabilities = {r: (1.0 if r == "D14" else 0.0) for r in dp.final_probabilities}
        desc = f"Matched supplied-account transfer {e.edge_id}"
        cp.rule_adjustments.append(RuleAdjustment("MA_INTERNAL_TRANSFER", "1.0.0", "INTERNAL_TRANSFER_ELIMINATION",
                                                  {"C04": 1.0}, desc))
        dp.rule_adjustments.append(RuleAdjustment("MA_INTERNAL_TRANSFER", "1.0.0", "INTERNAL_TRANSFER_ELIMINATION",
                                                  {"D14": 1.0}, desc))
        pair_graph.edges.append(e)


def compute_multi_account_features(accounts: list[AccountInput], txns: list[Transaction],
                                   predictions: dict[str, RolePrediction], internal_edges: list[PairEdge],
                                   eoc_by_account: dict[str, Decimal], cor_by_account: dict[str, Decimal]) -> dict:
    by_id = {t.transaction_id: t for t in txns}
    matched = sum((by_id[e.credit_txn_id].amount for e in internal_edges), ZERO)
    matched_ids = {i for e in internal_edges for i in (e.credit_txn_id, e.debit_txn_id)}
    unmatched_own = sum(
        (weighted(t.amount, predictions[t.transaction_id].p("C04", "D14")) for t in txns
         if t.transaction_id not in matched_ids), ZERO)
    gross = sum((t.amount for t in txns), ZERO)
    total_eoc = sum(eoc_by_account.values(), ZERO)
    shares = [float(v / total_eoc) for v in eoc_by_account.values()] if total_eoc else []
    hhi = sum(s * s for s in shares) if shares else None
    facility_ids = {a.account_id for a in accounts if a.account_type in (AccountType.OD, AccountType.CC)}
    facility_link = sum((by_id[e.debit_txn_id].amount for e in internal_edges
                         if e.evidence.get("from_account") in facility_ids), ZERO)
    missing_ratio = float(unmatched_own / gross) if gross else 0.0
    supplied = len(accounts)
    coverage_quality = "HIGH" if missing_ratio < 0.02 else "MEDIUM" if missing_ratio < 0.08 else "LOW"
    return {
        "MA01_MatchedInternalTransferAmount": float(matched),
        "MA02_UnmatchedOwnTransferSuspicion": float(unmatched_own),
        "MA03_ConsolidatedEOC": float(total_eoc),
        "MA04_ConsolidatedCOR": float(sum(cor_by_account.values(), ZERO)),
        "MA05_FacilityFundingLink": float(facility_link),
        "MA06_AccountFragmentationIndex": (1 - hhi) if hhi is not None else None,
        "MA07_PrimaryOperatingAccountShare": max(shares) if shares else None,
        "MA08_MissingAccountEvidence": missing_ratio,
        "MA09_ConsolidatedBalanceLiquidity": None,  # filled by the balance/liquidity engine
        "MA10_MultiAccountCoverageQuality": coverage_quality,
        "supplied_account_count": supplied,
    }
