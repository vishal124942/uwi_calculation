"use client";

import { CheckCircle2 } from "lucide-react";
import { useMemo } from "react";
import { fixed, inr, pct } from "@/lib/format";
import { rowsOf, sectionsOf } from "@/lib/trace";
import type { StepProps } from "./shared";
import { Legend, SeriesChart } from "../charts";
import { Badge, CalcLine, Card, CardBody, CardHeader, cx, Formula, KeyValueGrid, Note } from "../ui";

interface Candidate {
  series: string;
  label: string;
  value: number;
  weight: number;
}

/** Sort by value; the median is the first candidate whose cumulative weight reaches half the total. */
function weightedMedian(candidates: Candidate[]) {
  const sorted = candidates.filter((c) => c.weight > 0).sort((a, b) => a.value - b.value);
  const total = sorted.reduce((a, c) => a + c.weight, 0);
  const rows: (Candidate & { cumulative: number })[] = [];
  let acc = 0;
  let chosen = -1;
  for (const c of sorted) {
    acc += c.weight;
    if (chosen < 0 && acc >= total / 2) chosen = rows.length;
    rows.push({ ...c, cumulative: acc / total });
  }
  return { rows, chosen, total };
}

export default function Step08({ data }: StepProps) {
  const s = sectionsOf(data.tables.step08_sbci_and_legal);
  const sbci = s.s21_sbci ?? {};
  const legal = s.s16_legal_attribution ?? {};
  const monthly = useMemo(() => rowsOf(data.tables.step08_income_monthly_series), [data]);
  const rolling = useMemo(() => rowsOf(data.tables.step08_income_rolling_series), [data]);
  const income = (data.detail.income_parameters ?? {}) as Record<string, unknown>;
  const estimator = String(sbci.estimator ?? income.robust_estimator ?? "");

  const candidates = Object.values(s.s21_robust_centre_candidate ?? {}) as unknown as Candidate[];
  const ranked = weightedMedian(candidates);
  const min = Math.min(...candidates.map((c) => c.value), 0);
  const max = Math.max(...candidates.map((c) => c.value), 1);
  const x = (v: number) => `${((v - min) / (max - min || 1)) * 100}%`;
  const centre = sbci.robust_center as number;
  const recomputed = ranked.chosen >= 0 ? ranked.rows[ranked.chosen].value : null;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader title="From raw operating cash to sustainable income (Section 21)" subtitle="Each stage is reported, so the explainability bridge reconciles to the rupee" />
        <CardBody className="grid gap-6 lg:grid-cols-2">
          <div className="rounded-xl bg-white/[0.02] px-4 py-2">
            <CalcLine label="ROC, full-period monthly equivalent" value={inr(sbci.roc_basis_monthly, 2)} />
            <CalcLine op="±" label="cycle build-up / liquidation normalisation" value={inr(sbci.cycle_adjustment_basis_monthly, 2)} />
            <CalcLine op="=" label="CAOCG (cycle-adjusted)" value={inr(sbci.caocg_basis_monthly, 2)} emphasis />
            <div className="h-3" />
            <CalcLine label={`robust centre of candidate series (${estimator})`} value={inr(centre, 2)} />
            <CalcLine op="−" label="maintenance capex reserve" value={inr(sbci.maintenance_capex_reserve, 2)} />
            <CalcLine op="+" label="permitted adjustments" value={inr(sbci.permitted_adjustments, 2)} />
            <CalcLine op="=" label="SBCI · sustainable business cash income" value={inr(sbci.sbci_monthly, 2)} emphasis />
          </div>
          <div className="space-y-3">
            <Formula>
              CAOCG_month = ROC_month + (build − liquidation) × overlap(month, phase) ÷ phase_days
              <br />
              SBCI = max(0, robust_centre − maintenance_reserve + permitted_adjustments)
            </Formula>
            <Note>
              Candidates are every complete month of CAOCG (weight {String((income.candidate_weights as Record<string, number>)?.monthly ?? 1)}) plus the 90 / 180 / 365-day rolling
              monthly equivalents (weight {String((income.candidate_weights as Record<string, number>)?.rolling_90 ?? 2)} × window coverage). In a DECLINE regime the most recent
              months and the 90-day window are up-weighted; uncorroborated growth is capped at the 180-day window.
            </Note>
            <div className="flex flex-wrap gap-2">
              <Badge tone="info">trend regime {String(sbci.trend_regime)}</Badge>
              {(sbci.notes as string[] | undefined)?.map((n) => <Badge key={n}>{n}</Badge>)}
            </div>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Monthly ROC and cycle-adjusted CAOCG" subtitle="Bars show raw monthly operating cash; the line is after cycle normalisation" />
        <CardBody>
          <Legend items={[{ label: "ROC", color: "#38bdf8" }, { label: "CAOCG", color: "#fbbf24" }, { label: "SBCI", color: "#34d399", dashed: true }]} />
          <SeriesChart
            data={monthly}
            xKey="month"
            series={[
              { key: "roc", label: "ROC", color: "#38bdf8", type: "bar" },
              { key: "caocg", label: "CAOCG", color: "#fbbf24", type: "line" },
            ]}
            referenceY={[{ y: sbci.sbci_monthly as number, label: "SBCI", color: "#34d399" }]}
          />
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            {rolling.map((r) => (
              <div key={String(r.window)} className="rounded-xl bg-white/[0.02] px-4 py-3 text-xs">
                <div className="font-mono text-ink-300">{String(r.window)} · {fixed(r.months, 2)} months</div>
                <div className="mt-1 flex justify-between"><span className="text-ink-400">ROC / month</span><span className="font-mono tabular">{inr(r.roc_monthly_equivalent)}</span></div>
                <div className="flex justify-between"><span className="text-ink-400">CAOCG / month</span><span className="font-mono tabular">{inr(r.caocg_monthly_equivalent)}</span></div>
              </div>
            ))}
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title={`Robust centre: ${estimator.replace("_", " ")}`}
          subtitle="Sort the candidates by value, accumulate their weights; the centre is the first value where the running weight reaches half the total"
          right={
            recomputed !== null && estimator === "weighted_median" && Math.abs(recomputed - centre) < 0.01 ? (
              <Badge tone="good"><CheckCircle2 className="h-3 w-3" /> recomputed {inr(recomputed, 2)} = engine</Badge>
            ) : undefined
          }
        />
        <CardBody className="space-y-5">
          <div className="relative h-16 rounded-xl bg-white/[0.02]">
            <div className="absolute inset-x-4 top-1/2 h-px bg-white/10" />
            <div className="absolute inset-x-4 inset-y-0">
              {ranked.rows.map((c) => (
                <div
                  key={c.label}
                  title={`${c.label}: ${inr(c.value)} (w=${c.weight})`}
                  className={cx("absolute top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full", c.series.startsWith("rolling") ? "bg-violet-400/80" : "bg-sky-400/70")}
                  style={{ left: x(c.value), width: 6 + c.weight * 5, height: 6 + c.weight * 5 }}
                />
              ))}
              <div className="absolute inset-y-1 w-0.5 bg-emerald-400" style={{ left: x(centre) }} />
            </div>
          </div>
          <Legend items={[{ label: "monthly CAOCG", color: "#38bdf8" }, { label: "rolling-window equivalent", color: "#a78bfa" }, { label: "robust centre", color: "#34d399" }]} />
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-left text-ink-400">
                <tr className="border-b border-white/[0.06]">
                  <th className="py-2 pr-4 font-medium">Candidate</th>
                  <th className="py-2 pr-4 font-medium">Series</th>
                  <th className="py-2 pr-4 text-right font-medium">Value</th>
                  <th className="py-2 pr-4 text-right font-medium">Weight</th>
                  <th className="py-2 text-right font-medium">Cumulative weight</th>
                </tr>
              </thead>
              <tbody>
                {ranked.rows.map((c, i) => (
                  <tr key={c.label} className={cx("border-b border-white/[0.03]", i === ranked.chosen && "bg-emerald-400/10")}>
                    <td className="py-1.5 pr-4 font-mono text-ink-100">{c.label}</td>
                    <td className="py-1.5 pr-4 text-ink-400">{c.series}</td>
                    <td className="py-1.5 pr-4 text-right font-mono tabular">{inr(c.value, 2)}</td>
                    <td className="py-1.5 pr-4 text-right font-mono tabular">{fixed(c.weight, 3)}</td>
                    <td className="py-1.5 text-right font-mono tabular">
                      {pct(c.cumulative)} {i === ranked.chosen && <span className="ml-1 text-emerald-300">← crosses 50%</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardBody>
      </Card>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader
            title="Legal attribution (Section 16.2)"
            subtitle="Does the business cash belong to the borrower? Depends on the legal form and documents"
            right={<Badge tone={legal.status === "ATTRIBUTABLE" ? "good" : "warn"}>{String(legal.status)}</Badge>}
          />
          <CardBody className="space-y-3">
            <KeyValueGrid
              columns={1}
              data={Object.fromEntries(Object.entries(legal).filter(([k]) => k !== "notes"))}
              format={(k, v) => (/income/.test(k) ? inr(v, 2) : k === "confidence" ? pct(v) : String(v ?? "—"))}
            />
            <ul className="list-disc space-y-1 pl-5 text-xs text-ink-300">
              {(legal.notes as string[] | undefined)?.map((n) => <li key={n}>{n}</li>)}
            </ul>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Income features" subtitle="Registry features derived from the income series" />
          <CardBody>
            <KeyValueGrid data={s.s21_sbci_feature ?? {}} columns={1} format={(k, v) => (k.includes("MARGIN") ? pct(v) : inr(v, 2))} />
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
