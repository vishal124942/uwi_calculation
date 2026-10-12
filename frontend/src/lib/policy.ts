import { inr } from "./format";
import type { AnalysisResult, Policy } from "./types";

/** The value the policy rounded down to produce UWI, as a readable expression (mirrors s21_policy_engine). */
export function policySelection(u: NonNullable<AnalysisResult["underwriting"]>, policy?: Policy): { expression: string; value: number | null } {
  switch (u.selection_basis) {
    case "LOWER_BOUND":
      return { expression: `lower bound ${inr(u.lower_bound, 2)}`, value: u.lower_bound };
    case "CENTRAL":
      return { expression: `central ${inr(u.central_estimate, 2)}`, value: u.central_estimate };
    case "BLEND": {
      const w = policy?.blend_weight_central ?? 0.5;
      return {
        expression: `${w} × ${inr(u.central_estimate, 2)} + ${(1 - w).toFixed(2)} × ${inr(u.lower_bound, 2)}`,
        value: w * u.central_estimate + (1 - w) * u.lower_bound,
      };
    }
    case "DOCUMENTED_LEGAL_COMPONENTS":
      return { expression: `documented borrower income ${inr(u.borrower_income_monthly, 2)}`, value: u.borrower_income_monthly };
    default:
      return { expression: "no selection", value: null };
  }
}
