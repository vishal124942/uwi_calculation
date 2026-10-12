import type { AnalysisResult, Policy } from "./types";

/** Linear-interpolated quantile; mirrors `common.stats.quantile`. */
export function quantile(values: number[], q: number): number | null {
  const vals = [...values].sort((a, b) => a - b);
  if (!vals.length) return null;
  if (vals.length === 1) return vals[0];
  const pos = q * (vals.length - 1);
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  return vals[lo] * (1 - (pos - lo)) + vals[hi] * (pos - lo);
}

export type Basis = "LOWER_BOUND" | "BLEND" | "CENTRAL";

export interface WhatIfPolicy {
  basis: Basis;
  blendWeight: number;
  lowerQuantile: number;
  roundingUnit: number;
  minConfidence: number;
  deteriorationForce: number;
  referOnCoverage: boolean;
  referOnAnomaly: boolean;
  /** Stress test: scales SBCI and every bootstrap draw down by this share. */
  haircut: number;
}

export interface WhatIfInputs {
  central: number;
  distribution: number[];
  /** Engine lower bound, used when there is no bootstrap distribution (conformal / heuristic intervals). */
  lowerBound: number;
  outflowAllowance: number;
  confidence: number;
  deterioration: number;
  coverageRisk: string;
  anomalyReview: boolean;
  anomalyTriggers: string[];
}

export interface WhatIfOutcome {
  central: number;
  lower: number;
  selected: number;
  basis: Basis;
  forcedLower: boolean;
  uwi: number;
  status: string;
  reasons: string[];
}

export function policyFromMeta(p: Policy): WhatIfPolicy {
  return {
    basis: (["LOWER_BOUND", "BLEND", "CENTRAL"].includes(p.estimate_basis) ? p.estimate_basis : "LOWER_BOUND") as Basis,
    blendWeight: p.blend_weight_central,
    lowerQuantile: p.lower_quantile,
    roundingUnit: p.rounding_unit,
    minConfidence: p.min_confidence_auto_decision,
    deteriorationForce: p.deterioration_force_lower_bound,
    referOnCoverage: p.refer_on_high_coverage_risk,
    referOnAnomaly: p.refer_on_anomaly,
    haircut: 0,
  };
}

const roundDown = (v: number, unit: number) => (unit <= 1 ? v : Math.floor(v / unit + 1e-9) * unit);

/** M8 lower bound and M9 `policy_select` + referral order, recomputed for a hypothetical policy. */
export function evaluate(inputs: WhatIfInputs, p: WhatIfPolicy): WhatIfOutcome {
  const scale = 1 - p.haircut;
  const central = inputs.central * scale;
  const draw = quantile(inputs.distribution.map((d) => d * scale), p.lowerQuantile);
  const rawLower = draw === null ? inputs.lowerBound * scale : draw - inputs.outflowAllowance;
  const lower = Math.max(0, Math.min(rawLower, central));

  const forcedLower = inputs.deterioration >= p.deteriorationForce && p.basis !== "LOWER_BOUND";
  const basis: Basis = inputs.deterioration >= p.deteriorationForce ? "LOWER_BOUND" : p.basis;
  const selected = basis === "CENTRAL" ? central : basis === "BLEND" ? p.blendWeight * central + (1 - p.blendWeight) * lower : lower;

  let status = "SUCCESS";
  const reasons: string[] = [];
  if (central <= 0) status = "NO_SUSTAINABLE_INCOME";
  else if (p.referOnAnomaly && inputs.anomalyReview) {
    status = "REFER_ANOMALY";
    reasons.push(...inputs.anomalyTriggers);
  } else if (p.referOnCoverage && (inputs.coverageRisk === "HIGH" || inputs.coverageRisk === "INDETERMINATE")) {
    status = "REFER_COVERAGE_RISK";
    reasons.push(`coverage_risk=${inputs.coverageRisk}`);
  } else if (inputs.confidence < p.minConfidence) {
    status = "REFER_LOW_CONFIDENCE";
    reasons.push(`confidence=${inputs.confidence.toFixed(2)} < ${p.minConfidence}`);
  }
  return { central, lower, selected, basis, forcedLower, uwi: central <= 0 ? 0 : roundDown(selected, p.roundingUnit), status, reasons };
}

/** Whether the result can be re-decided by policy alone (legal attribution and account structure gates aside). */
export function whatIfSupported(r: AnalysisResult): boolean {
  const u = r.underwriting;
  return !!u && u.underwriting_income_monthly !== null && u.selection_basis !== "DOCUMENTED_LEGAL_COMPONENTS" && u.selection_basis !== "NONE";
}
