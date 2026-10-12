"use client";

import { CheckCircle2, FlaskConical, RotateCcw, TriangleAlert } from "lucide-react";
import { useMemo, useState } from "react";
import { riskSignals } from "@/lib/insights";
import { inr, num, pct } from "@/lib/format";
import type { TraceState } from "@/lib/trace";
import type { Policy } from "@/lib/types";
import { type Basis, evaluate, policyFromMeta, type WhatIfInputs, type WhatIfPolicy } from "@/lib/whatif";
import { Histogram } from "./charts";
import { CountUp } from "./motion";
import { Badge, Card, CardBody, CardHeader, cx, statusTone } from "./ui";

function Slider({
  label,
  value,
  min,
  max,
  step,
  format,
  onChange,
  hint,
  disabled,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  format: (v: number) => string;
  onChange: (v: number) => void;
  hint?: React.ReactNode;
  disabled?: boolean;
}) {
  return (
    <label className={cx("block", disabled && "pointer-events-none opacity-40")}>
      <div className="flex items-baseline justify-between text-xs">
        <span className="text-ink-200">{label}</span>
        <span className="font-mono text-ink-100 tabular">{format(value)}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-1.5 h-1.5 w-full cursor-pointer appearance-none rounded-full bg-white/10 accent-sky-400"
      />
      {hint && <div className="mt-1 text-[11px] text-ink-400">{hint}</div>}
    </label>
  );
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button type="button" onClick={() => onChange(!checked)} className="flex w-full items-center justify-between gap-3 text-xs text-ink-200">
      {label}
      <span className={cx("relative h-4 w-7 rounded-full transition", checked ? "bg-sky-400/70" : "bg-white/10")}>
        <span className={cx("absolute top-0.5 h-3 w-3 rounded-full bg-white transition-all", checked ? "left-3.5" : "left-0.5")} />
      </span>
    </button>
  );
}

const BASES: { id: Basis; label: string }[] = [
  { id: "LOWER_BOUND", label: "Lower bound" },
  { id: "BLEND", label: "Blend" },
  { id: "CENTRAL", label: "Central" },
];

export default function PolicyLab({ trace, policy }: { trace: TraceState; policy: Policy }) {
  const r = trace.result!;
  const u = r.underwriting!;
  const engine = useMemo(() => policyFromMeta(policy), [policy]);
  const [p, setP] = useState<WhatIfPolicy>(engine);
  const set = (patch: Partial<WhatIfPolicy>) => setP((x) => ({ ...x, ...patch }));

  const inputs: WhatIfInputs = useMemo(() => {
    const detail = trace.steps.step09_uncertainty_and_policy?.detail ?? {};
    const anomaly = riskSignals(trace).s19_anomaly ?? {};
    return {
      central: u.central_estimate,
      distribution: Array.isArray(detail.distribution) ? (detail.distribution as number[]) : [],
      lowerBound: u.lower_bound,
      outflowAllowance: u.interval_method.startsWith("CONFORMAL") ? 0 : u.unresolved_outflow_allowance_monthly,
      confidence: u.confidence,
      deterioration: num(detail.recent_deterioration) ?? 0,
      coverageRisk: u.coverage_risk,
      anomalyReview: anomaly.review_required === true,
      anomalyTriggers: Array.isArray(anomaly.triggers) ? (anomaly.triggers as string[]) : [],
    };
  }, [trace, u]);

  const out = evaluate(inputs, p);
  const atEngine = JSON.stringify(p) === JSON.stringify(engine);
  const reproduces = evaluate(inputs, engine).uwi === u.underwriting_income_monthly;
  const delta = out.uwi - (u.underwriting_income_monthly ?? 0);
  const hasDraws = inputs.distribution.length > 0;
  const draws = useMemo(() => inputs.distribution.map((d) => d * (1 - p.haircut)), [inputs.distribution, p.haircut]);

  return (
    <Card>
      <CardHeader
        title={
          <span className="inline-flex items-center gap-2">
            <FlaskConical className="h-4 w-4 text-violet-300" /> Policy lab: what if the lender&apos;s policy were different?
          </span>
        }
        subtitle={`Recomputes the M8 lower bound and the M9 policy selection in your browser from this run's ${inputs.distribution.length || "no"} bootstrap draws. The economic model is not re-run.`}
        right={
          <button
            onClick={() => setP(engine)}
            disabled={atEngine}
            className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1 text-xs text-ink-200 transition hover:bg-white/5 disabled:opacity-30"
          >
            <RotateCcw className="h-3.5 w-3.5" /> Engine policy
          </button>
        }
      />
      <CardBody className="grid gap-8 lg:grid-cols-[minmax(0,22rem)_1fr]">
        <div className="space-y-5">
          <div>
            <div className="mb-1.5 text-xs text-ink-200">Estimate the policy selects</div>
            <div className="grid grid-cols-3 rounded-xl border border-white/[0.07] bg-ink-950/50 p-1">
              {BASES.map((b) => (
                <button
                  key={b.id}
                  onClick={() => set({ basis: b.id })}
                  className={cx("rounded-lg py-1.5 text-xs font-medium transition", p.basis === b.id ? "bg-violet-400/20 text-violet-100" : "text-ink-300 hover:text-ink-100")}
                >
                  {b.label}
                </button>
              ))}
            </div>
          </div>
          {p.basis === "BLEND" && (
            <Slider label="Weight on central estimate" value={p.blendWeight} min={0} max={1} step={0.05} format={(v) => pct(v, 0)} onChange={(v) => set({ blendWeight: v })} />
          )}
          <Slider
            label="Lower-bound quantile"
            value={p.lowerQuantile}
            min={0.01}
            max={0.5}
            step={0.01}
            format={(v) => `P${Math.round(v * 100)}`}
            onChange={(v) => set({ lowerQuantile: v })}
            disabled={!hasDraws}
            hint={hasDraws ? "Lower = this quantile of the bootstrap draws − unresolved-outflow allowance" : `${u.interval_method}: no bootstrap draws to re-sample`}
          />
          <Slider
            label="Stress: haircut on sustainable income"
            value={p.haircut}
            min={0}
            max={0.5}
            step={0.01}
            format={(v) => (v ? `−${pct(v, 0)}` : "none")}
            onChange={(v) => set({ haircut: v })}
            hint="Scales SBCI and every bootstrap draw down"
          />
          <Slider
            label="Minimum confidence for auto-decision"
            value={p.minConfidence}
            min={0.3}
            max={0.95}
            step={0.01}
            format={(v) => pct(v, 0)}
            onChange={(v) => set({ minConfidence: v })}
            hint={`This run's confidence: ${pct(inputs.confidence)}`}
          />
          <Slider
            label="Deterioration score that forces the lower bound"
            value={p.deteriorationForce}
            min={0.05}
            max={1}
            step={0.05}
            format={(v) => v.toFixed(2)}
            onChange={(v) => set({ deteriorationForce: v })}
            hint={`This run's recent-deterioration score: ${inputs.deterioration.toFixed(2)}`}
          />
          <div className="flex items-center justify-between text-xs">
            <span className="text-ink-200">Round down to</span>
            <select
              value={p.roundingUnit}
              onChange={(e) => set({ roundingUnit: Number(e.target.value) })}
              className="rounded-lg border border-white/10 bg-ink-850 px-2 py-1 text-xs text-ink-100"
            >
              {[1, 100, 500, 1000, 5000].map((v) => (
                <option key={v} value={v}>{v === 1 ? "no rounding" : inr(v)}</option>
              ))}
            </select>
          </div>
          <div className="space-y-2.5 border-t border-white/[0.06] pt-4">
            <Toggle label="Refer on high coverage risk" checked={p.referOnCoverage} onChange={(v) => set({ referOnCoverage: v })} />
            <Toggle label="Refer when anomaly review is required" checked={p.referOnAnomaly} onChange={(v) => set({ referOnAnomaly: v })} />
          </div>
        </div>

        <div className="min-w-0">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <div className="text-[11px] uppercase tracking-[0.16em] text-ink-400">What-if underwriting income</div>
              <div className="mt-1 text-5xl font-semibold tracking-tight text-violet-100">
                <CountUp value={out.uwi} format={(v) => inr(v)} duration={450} />
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                <Badge tone={statusTone(out.status)}>{out.status}</Badge>
                <Badge tone="policy">{out.basis}</Badge>
                {delta !== 0 && (
                  <span className={cx("font-mono tabular", delta > 0 ? "text-emerald-300" : "text-rose-300")}>
                    {delta > 0 ? "+" : "−"}
                    {inr(Math.abs(delta))} vs engine ({inr(u.underwriting_income_monthly)})
                  </span>
                )}
                {delta === 0 && !atEngine && <span className="text-ink-400">same as engine</span>}
              </div>
            </div>
            <div className="text-right text-xs text-ink-300">
              {atEngine &&
                (reproduces ? (
                  <span className="inline-flex items-center gap-1.5 text-emerald-300">
                    <CheckCircle2 className="h-3.5 w-3.5" /> Reproduces the engine&apos;s UWI exactly
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1.5 text-amber-300">
                    <TriangleAlert className="h-3.5 w-3.5" /> Differs from the engine (rounded draws)
                  </span>
                ))}
            </div>
          </div>

          <div className="mt-4 rounded-xl border border-violet-400/20 bg-violet-400/[0.05] px-4 py-3 font-mono text-[12.5px] leading-relaxed text-violet-100">
            {out.basis === "CENTRAL"
              ? `UWI = floor( central ${inr(out.central, 2)} ÷ ${p.roundingUnit} ) × ${p.roundingUnit}`
              : out.basis === "BLEND"
                ? `UWI = floor( (${p.blendWeight.toFixed(2)} × ${inr(out.central, 2)} + ${(1 - p.blendWeight).toFixed(2)} × ${inr(out.lower, 2)}) ÷ ${p.roundingUnit} ) × ${p.roundingUnit}`
                : `UWI = floor( lower ${inr(out.lower, 2)} ÷ ${p.roundingUnit} ) × ${p.roundingUnit}`}
            {" "}= {inr(out.uwi)}
            {out.forcedLower && <div className="mt-1 text-amber-200">Recent deterioration ≥ threshold, so the policy is forced to the lower bound.</div>}
            {out.reasons.length > 0 && <div className="mt-1 text-amber-200">Referral: {out.reasons.join("; ")}</div>}
          </div>

          {hasDraws ? (
            <div className="mt-4">
              <Histogram
                values={draws}
                bins={36}
                height={230}
                markers={[
                  { x: out.lower, label: "Lower", color: "#fb7185" },
                  { x: out.central, label: "SBCI", color: "#34d399" },
                  { x: out.uwi, label: "UWI", color: "#a78bfa" },
                ]}
              />
              <div className="mt-1 text-[11px] text-ink-400">
                Bootstrap distribution of sustainable income (M8). The lower bound is the selected quantile minus the unresolved-outflow allowance of{" "}
                {inr(inputs.outflowAllowance)}.
              </div>
            </div>
          ) : (
            <div className="mt-4 text-xs text-ink-400">This run&apos;s interval ({u.interval_method}) has no bootstrap draws; the lower bound is the engine&apos;s.</div>
          )}
        </div>
      </CardBody>
    </Card>
  );
}
