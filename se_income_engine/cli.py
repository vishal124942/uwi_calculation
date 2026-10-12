"""Command-line runner: analyse one or more statement files end to end.

Example:
    python -m se_income_engine.cli statement.xlsx --legal-owner-type SOLE_PROP --out result.json
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from se_income_engine.contracts.enums import AccountType, LegalOwnerType
from se_income_engine.pipeline.analyse import analyse_self_employed_income
from se_income_engine.pipeline.context import AnalysisRequest, BorrowerContext
from se_income_engine.services.m1_parser_normaliser.s03_statement_parsers import parse_statement_file
from se_income_engine.services.supporting.audit_explainability.s25_audit_persistence import AuditStore


def _print_summary(result: dict) -> None:
    print(f"\nanalysis_id : {result['analysis_id']}")
    print(f"status      : {result['status']}")
    if not result.get("economic_outputs"):
        for flag in result.get("flags", []):
            print(f"  - {flag}")
        return
    print(f"basis       : {result['economic_outputs']['basis']}")
    print("\nEconomic bridge (INR / month)")
    for line in result["bridge"]:
        print(f"  {line['line']:<66} {line['monthly_amount']:>14,.2f}")
    u = result["underwriting"]
    print(f"\nUWI {u['underwriting_income_monthly']}  central {u['central_estimate']}  "
          f"interval [{u['lower_bound']}, {u['upper_bound']}]  confidence {u['confidence']}")
    print(f"coverage_risk {u['coverage_risk']}  legal {u['legal_attribution_status']}  "
          f"archetype {result['archetype']['code']}  cycle {result['cycle']['status']}  trend {result['trend']['regime']}")
    if result["reasons"]:
        print("reason codes: " + ", ".join(f"{r['code']} {r['reason']}" for r in result["reasons"]))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Self-Employed Income Reconstruction Engine")
    ap.add_argument("files", nargs="+", type=Path, help="statement files (analyser .xlsx or generic .csv)")
    ap.add_argument("--customer-id", default="CUSTOMER-001")
    ap.add_argument("--application-id", default="APP-001")
    ap.add_argument("--as-of", type=date.fromisoformat, default=None)
    ap.add_argument("--application-date", type=date.fromisoformat, default=None)
    ap.add_argument("--account-type", choices=[e.value for e in AccountType], default="SAVINGS")
    ap.add_argument("--legal-owner-type", choices=[e.value for e in LegalOwnerType], default="SOLE_PROP")
    ap.add_argument("--policy-id", default="SE_INCOME_POLICY_001")
    ap.add_argument("--audit-db", type=Path, default=None, help="SQLite audit store path")
    ap.add_argument("--out", type=Path, default=None, help="write full JSON response")
    args = ap.parse_args(argv)

    legal = LegalOwnerType(args.legal_owner_type)
    accounts = [parse_statement_file(f, args.customer_id, AccountType(args.account_type), legal) for f in args.files]
    as_of = args.as_of or max(a.statement_end for a in accounts)
    request = AnalysisRequest(
        customer_id=args.customer_id,
        application_id=args.application_id,
        as_of_date=as_of,
        accounts=accounts,
        borrower_context=BorrowerContext(legal_owner_type=legal, application_date=args.application_date or as_of),
        policy_id=args.policy_id,
    )
    store = AuditStore(args.audit_db) if args.audit_db else None
    result = analyse_self_employed_income(request, store=store)
    _print_summary(result)
    if args.out:
        args.out.write_text(json.dumps(result, indent=2, default=str))
        print(f"\nfull response written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
