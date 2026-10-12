"use client";

import { CheckCircle2, CircleDot, OctagonX } from "lucide-react";
import { featureName, fixed, inr, pct } from "@/lib/format";
import { sectionsOf } from "@/lib/trace";
import type { Policy } from "@/lib/types";
import type { StepProps } from "./shared";
import { ConfidenceRadar, Histogram } from "../charts";
import { Badge, CalcLine, Card, CardBody, CardHeader, cx, Formula, Note, statusTone } from "../ui";

interface Gate {
  label: string;
  detail: string;
  fired: boolean;
  outcome: string;
  skipped?: boolean;
}

/** Pipeline step 9 is shared: part "uncertainty" is M8, part "policy" is M9. */
export default function Step09({ data, trace, part }: StepProps) {
  const showUncertainty = part !== "policy";
  const showPolicy = part !== "uncertainty";
  const s = sectionsOf(data.tables.step09_uncertainty_and_policy);
  const u = s.s22_uncertainty ?? {};
  const dims = (s.s22_confidence_dimension ?? {}) as Record<string, number>;
  const decision = s.s21_policy_decision ?? {};
  const weights = (data.detail.confidence_weights ?? {}) as Record<string, number>;
  const policy = data.detail.policy as unknown as Policy | undefined;
  const uncParams = (data.detail.uncertainty_parameters ?? {}) as Record<string, number>;
  const distribution = (data.detail.distribution ?? []) as number[];
  const deterioration = (data.detail.recent_deterioration as number | null) ?? 0;

  const risk = sectionsOf(trace.steps.step07_risk_signals?.tables.step07_risk_signals);
  const income = sectionsOf(trace.steps.step08_income_and_legal_attribution?.tables.step08_sbci_and_legal);
  const legalStatus = String(income.s16_legal_attribution?.status ?? "");
  const sbci = income.s21_sbci?.sbci_monthly as number;
  const coverageRisk = String(risk.s20_coverage?.risk ?? "");
  const anomalyReview = risk.s19_anomaly?.review_required === true;
  const accounts = trace.request?.accounts ?? [];

  const rows = Object.entries(dims).map(([k, v]) => {
    const w = weights[k.slice(0, 4)] ?? 1;
    const ln = Math.log(Math.max(0.01, v));
    return { key: k, value: v, weight: w, ln, contribution: w * ln };
  });
  const sumW = rows.reduce((a, r) => a + r.weight, 0);
  const sumC = rows.reduce((a, r) => a + r.contribution, 0);
  const confidence = u.confidence as number;
  const central = u.central as number;
  const lower = u.lower as number;
  const upper = u.upper as number;
  const lowerRaw = u.lower_before_allowance as number;
  const upperRaw = u.upper_before_allowance as number;
  const method = String(u.interval_method ?? "");
  const unit = policy?.rounding_unit ?? 100;
  const forced = policy ? deterioration >= policy.deterioration_force_lower_bound : false;
  const basis = String(decision.basis ?? "");
  const selected = basis === "LOWER_BOUND" ? lower : basis === "CENTRAL" ? central : basis === "BLEND" ? (policy?.blend_weight_central ?? 0.5) * central + (1 - (policy?.blend_weight_central ?? 0.5)) * lower : null;

  const gates: Gate[] = [];
  const odOnly = accounts.length > 0 && accounts.every((a) => a.account_type === "OD" || a.account_type === "CC");
  gates.push({ label: "Standalone income source", detail: "all supplied accounts are OD/CC facilities?", fired: odOnly, outcome: "UNSUPPORTED_ACCOUNT_STRUCTURE" });
  gates.push({ label: "Positive sustainable income", detail: `SBCI ${inr(sbci, 2)} ≤ 0?`, fired: !(sbci > 0), outcome: "NO_SUSTAINABLE_INCOME", skipped: odOnly });
  const legalStop = legalStatus === "NEEDS_LEGAL_ATTRIBUTION" || legalStatus === "FIRM_CASH_INCOME_ONLY";
  gates.push({ label: "Legal attribution", detail: `status ${legalStatus}`, fired: legalStop, outcome: "REFER_LEGAL_ATTRIBUTION", skipped: odOnly || !(sbci > 0) });
  const early = odOnly || !(sbci > 0) || legalStop;
  const anomalyFired = !!policy?.refer_on_anomaly && anomalyReview;
  gates.push({ label: "Anomaly review", detail: `review_required = ${anomalyReview}${policy?.refer_on_anomaly ? "" : " (policy ignores)"}`, fired: anomalyFired, outcome: "REFER_ANOMALY", skipped: early });
  const covFired = !!policy?.refer_on_high_coverage_risk && (coverageRisk === "HIGH" || coverageRisk === "INDETERMINATE");
  gates.push({ label: "Coverage risk", detail: `coverage risk ${coverageRisk}`, fired: covFired, outcome: "REFER_COVERAGE_RISK", skipped: early || anomalyFired });
  gates.push({
    label: "Confidence for automatic decision",
    detail: `${pct(confidence, 2)} < ${pct(policy?.min_confidence_auto_decision ?? 0.6, 0)}?`,
    fired: confidence < (policy?.min_confidence_auto_decision ?? 0.6),
    outcome: "REFER_LOW_CONFIDENCE",
    skipped: early || anomalyFired || covFired,
  });

  return (
    <div className="space-y-6">
      {showUncertainty && (
        <>
          <div className="grid gap-6 xl:grid-cols-[1.3fr_1fr]">
            <Card>
              <CardHeader title="Confidence (Section 22.1): weighted geometric mean of CF01–CF10" subtitle="One weak dimension pulls confidence down much more than in an arithmetic average" />
              <CardBody className="space-y-4">
                <Formula>confidence = exp( Σ wᵢ · ln(max(0.01, CFᵢ)) ÷ Σ wᵢ )</Formula>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead className="text-left text-ink-400">
                      <tr className="border-b border-white/[0.06]">
                        <th className="py-2 pr-4 font-medium">Dimension</th>
                        <th className="py-2 pr-4 text-right font-medium">CF</th>
                        <th className="py-2 pr-4 text-right font-medium">weight w</th>
                        <th className="py-2 pr-4 text-right font-medium">ln CF</th>
                        <th className="py-2 text-right font-medium">w · ln CF</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r) => (
                        <tr key={r.key} className="border-b border-white/[0.03]">
                          <td className="py-1.5 pr-4 text-ink-200">
                            <span className="mr-1.5 font-mono text-ink-400">{r.key.slice(0, 4)}</span>
                            {featureName(r.key).label}
                          </td>
                          <td className="py-1.5 pr-4 text-right font-mono tabular">
                            <span className={r.value < 0.5 ? "text-rose-300" : r.value < 0.75 ? "text-amber-300" : "text-emerald-300"}>{r.value.toFixed(4)}</span>
                          </td>
                          <td className="py-1.5 pr-4 text-right font-mono tabular">{r.weight}</td>
                          <td className="py-1.5 pr-4 text-right font-mono tabular">{r.ln.toFixed(4)}</td>
                          <td className="py-1.5 text-right font-mono tabular">{r.contribution.toFixed(4)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="rounded-xl bg-white/[0.02] px-4 py-2">
                  <CalcLine label="Σ w · ln CF" value={sumC.toFixed(4)} />
                  <CalcLine op="÷" label="Σ w" value={sumW.toFixed(2)} />
                  <CalcLine op="=" label="mean log" value={(sumC / sumW).toFixed(4)} />
                  <CalcLine op="exp" label="confidence" value={`${Math.exp(sumC / sumW).toFixed(4)}  (engine ${confidence.toFixed(4)})`} emphasis />
                </div>
              </CardBody>
            </Card>
            <Card>
              <CardHeader title="Confidence profile" subtitle={`Segment ${String(u.segment ?? "")}`} />
              <CardBody>
                <ConfidenceRadar dims={dims} height={340} />
              </CardBody>
            </Card>
          </div>

          <Card>
            <CardHeader title={`Income interval (Section 22.3): ${method}`} subtitle={(u.notes as string[] | undefined)?.join(" · ")} />
            <CardBody className="grid gap-6 xl:grid-cols-[1.4fr_1fr]">
              <div className="space-y-3">
                {method === "BOOTSTRAP_UNCALIBRATED" && (
                  <>
                    <Formula>
                      bᵢ = trimmed mean ({pct(uncParams.bootstrap_trim_fraction ?? 0.1, 0)}) of a moving-block resample ({uncParams.bootstrap_block_months ?? 3}-month blocks) of monthly CAOCG, i = 1…{uncParams.bootstrap_iterations ?? 400}
                      <br />
                      distᵢ = SBCI + (bᵢ − median(b)) × (1 + (1 − confidence)) &nbsp;·&nbsp; lower = P{Math.round((policy?.lower_quantile ?? 0.1) * 100)}, upper = P{Math.round((policy?.upper_quantile ?? 0.9) * 100)}
                    </Formula>
                    <Histogram
                      values={distribution}
                      markers={[
                        { x: lowerRaw, label: `P${Math.round((policy?.lower_quantile ?? 0.1) * 100)}`, color: "#fbbf24" },
                        { x: central, label: "SBCI", color: "#34d399" },
                        { x: upperRaw, label: `P${Math.round((policy?.upper_quantile ?? 0.9) * 100)}`, color: "#38bdf8" },
                        { x: lower, label: "lower bound", color: "#fb7185" },
                      ]}
                    />
                    <Note>Width multiplier for this run: 1 + (1 − {confidence.toFixed(4)}) = {(2 - confidence).toFixed(4)}. Lower confidence widens the interval.</Note>
                  </>
                )}
                {method === "HEURISTIC_UNCALIBRATED" && <Formula>half-width = SBCI × (1 − confidence) · lower = SBCI − half-width · upper = SBCI + half-width (fewer than 3 complete months)</Formula>}
                {method.startsWith("CONFORMAL") && <Formula>lower = SBCI × (1 − q_lo[segment]) · upper = SBCI × (1 + q_hi[segment]) from the calibrated conformal artifact</Formula>}
              </div>
              <div className="space-y-4">
                <div className="rounded-xl bg-white/[0.02] px-4 py-2">
                  <CalcLine label="interval lower quantile" value={inr(lowerRaw, 2)} />
                  <CalcLine op="−" label="unresolved-outflow allowance" value={inr(u.unresolved_outflow_allowance, 2)} note="unknown debits that may be operating" />
                  <CalcLine op="=" label="lower bound (clamped to [0, SBCI])" value={inr(lower, 2)} emphasis />
                  <div className="h-2" />
                  <CalcLine label="interval upper quantile" value={inr(upperRaw, 2)} />
                  <CalcLine op="+" label="unresolved-inflow allowance" value={inr(u.unresolved_inflow_allowance, 2)} />
                  <CalcLine op="=" label="upper bound (≥ SBCI)" value={inr(upper, 2)} emphasis />
                </div>
                <Note>
                  The allowances carry the operating share of unknown-role money: unknown debits × (COR ÷ resolved debits) plus non-recurring COR, per month.
                  Losing evidence can therefore only lower the lower bound, never raise it.
                </Note>
              </div>
            </CardBody>
          </Card>
        </>
      )}

      {showPolicy && (
        <div className="grid gap-6 xl:grid-cols-2">
          <Card>
            <CardHeader
              title="Policy decision (Section 21.5)"
              subtitle={policy ? `${policy.policy_id} v${policy.policy_version} · estimate basis ${policy.estimate_basis} · rounding ₹${unit}` : undefined}
              right={<Badge tone={statusTone(String(decision.status))}>{String(decision.status)}</Badge>}
            />
            <CardBody className="space-y-4">
              <div className="rounded-xl bg-white/[0.02] px-4 py-2">
                <CalcLine label="central estimate (M7 SBCI)" value={inr(central, 2)} />
                <CalcLine label="lower bound (M8)" value={inr(lower, 2)} />
                <CalcLine label="confidence (M8)" value={pct(confidence, 2)} />
                <div className="my-1 border-t border-white/[0.05]" />
                <CalcLine
                  label="selection basis"
                  value={basis}
                  note={forced ? `forced: deterioration ${fixed(deterioration, 3)} ≥ ${policy?.deterioration_force_lower_bound}` : `recent deterioration ${fixed(deterioration, 3)}`}
                />
                {selected !== null && <CalcLine label="selected estimate" value={inr(selected, 2)} />}
                {selected !== null && <CalcLine op="÷" label="rounding unit" value={`₹${unit}`} />}
                {selected !== null && <CalcLine op="⌊⌋" label="floor" value={Math.floor(selected / unit).toLocaleString("en-IN")} />}
                {selected !== null && <CalcLine op="×" label="rounding unit" value={`₹${unit}`} />}
                <CalcLine op="=" label="UWI · underwriting income / month" value={inr(decision.underwriting_income_monthly)} emphasis />
              </div>
              <Note>UWI is always rounded down, so it never exceeds the chosen estimate.</Note>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Decision gates, in the order the policy engine evaluates them" subtitle="The first three stop the analysis with no UWI; the last three keep the computed UWI but route it to a reviewer. The first gate that fires sets the status." />
            <CardBody className="space-y-2">
              {gates.map((g) => (
                <div
                  key={g.label}
                  className={cx(
                    "flex items-start gap-3 rounded-xl border px-4 py-3 text-xs",
                    g.skipped ? "border-white/[0.04] opacity-40" : g.fired ? "border-amber-400/30 bg-amber-400/[0.05]" : "border-white/[0.06] bg-white/[0.02]",
                  )}
                >
                  {g.skipped ? <CircleDot className="mt-0.5 h-4 w-4 text-ink-500" /> : g.fired ? <OctagonX className="mt-0.5 h-4 w-4 text-amber-300" /> : <CheckCircle2 className="mt-0.5 h-4 w-4 text-emerald-300" />}
                  <div className="flex-1">
                    <div className="font-medium text-ink-100">{g.label}</div>
                    <div className="text-ink-400">{g.detail}</div>
                  </div>
                  <span className={cx("font-mono text-[11px]", g.fired && !g.skipped ? "text-amber-200" : "text-ink-500")}>{g.fired && !g.skipped ? g.outcome : g.skipped ? "not reached" : "pass"}</span>
                </div>
              ))}
              {(decision.referral_reasons as string[] | undefined)?.length ? (
                <div className="text-xs text-amber-200">Referral reasons: {(decision.referral_reasons as string[]).join("; ")}</div>
              ) : null}
            </CardBody>
          </Card>
        </div>
      )}
    </div>
  );
}
