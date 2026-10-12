"use client";

import { AlertTriangle, ArrowRight, Info } from "lucide-react";
import { useState } from "react";
import { componentsInStep } from "@/lib/components";
import { featureName, inr, ms, pct } from "@/lib/format";
import { policySelection } from "@/lib/policy";
import { sectionsOf } from "@/lib/trace";
import type { Meta } from "@/lib/types";
import type { TraceState } from "@/lib/trace";
import { StoryCards } from "./BusinessStory";
import { BridgeWaterfall, ConfidenceRadar, IntervalBand, Legend, SeriesChart } from "./charts";
import { ComponentChip } from "./ComponentView";
import MoneyFlow from "./MoneyFlow";
import { CountUp } from "./motion";
import PolicyLab from "./PolicyLab";
import type { View } from "./Sidebar";
import { Badge, Card, CardBody, CardHeader, riskTone, statusTone, Tabs } from "./ui";

export default function Overview({
  trace,
  meta,
  onView,
  onOpenTxn,
}: {
  trace: TraceState;
  meta: Meta | null;
  onView: (v: View) => void;
  onOpenTxn: (id: string) => void;
}) {
  const r = trace.result!;
  const u = r.underwriting!;
  const eo = r.economic_outputs ?? {};
  const unc = sectionsOf(trace.steps.step09_uncertainty_and_policy?.tables.step09_uncertainty_and_policy).s22_uncertainty ?? {};
  const policy = meta?.policies.find((p) => r.policy_version.startsWith(p.policy_id));
  const steps = meta?.steps ?? [];
  const maxMs = Math.max(...steps.map((s) => trace.steps[s.id]?.compute_ms ?? 0), 1);
  const [bridgeView, setBridgeView] = useState<"flow" | "waterfall">("flow");

  return (
    <div className="space-y-6">
      {/* Hero */}
      <div className="grid gap-4 xl:grid-cols-[1.25fr_1fr]">
        <Card className="gradient-ring overflow-hidden">
          <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-violet-500/20 blur-3xl" />
          <div className="pointer-events-none absolute -bottom-28 -left-16 h-64 w-64 rounded-full bg-sky-500/10 blur-3xl" />
          <div className="relative p-7">
            <div className="flex items-center gap-2">
              <Badge tone={statusTone(r.status)}>{r.status}</Badge>
              <Badge tone="policy">{u.selection_basis}</Badge>
              <span className="font-mono text-[11px] text-ink-400">{r.analysis_id}</span>
            </div>
            <div className="mt-5 text-xs font-medium uppercase tracking-[0.18em] text-ink-300">Underwriting income (UWI) per month</div>
            <div className="mt-1 bg-gradient-to-r from-white via-violet-100 to-sky-200 bg-clip-text text-6xl font-semibold tracking-tight text-transparent tabular">
              {u.underwriting_income_monthly === null ? "—" : <CountUp value={u.underwriting_income_monthly} format={(v) => inr(v)} duration={1400} />}
            </div>
            <div className="mt-4 rounded-xl border border-violet-400/20 bg-violet-400/[0.06] px-4 py-3 font-mono text-[13px] text-violet-100">
              UWI = floor( {policySelection(u, policy).expression} ÷ {policy?.rounding_unit ?? 100} ) × {policy?.rounding_unit ?? 100} ={" "}
              {inr(u.underwriting_income_monthly)}
            </div>
            <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <MiniStat label="Central (SBCI)" value={<CountUp value={u.central_estimate} format={(v) => inr(v)} duration={1400} />} />
              <MiniStat label="80% interval" value={`${inr(u.lower_bound)} – ${inr(u.upper_bound)}`} />
              <MiniStat label="Confidence" value={<CountUp value={u.confidence} format={(v) => pct(v)} duration={1400} />} />
              <MiniStat label="Post-debt free cash" value={inr(eo.post_debt_free_cash_monthly)} />
            </div>
            {u.referral_reasons.length > 0 && (
              <div className="mt-4 flex items-start gap-2 rounded-lg bg-amber-400/[0.07] px-3 py-2 text-xs text-amber-200">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> Referral: {u.referral_reasons.join("; ")}
              </div>
            )}
          </div>
        </Card>

        <Card>
          <CardHeader title="Where the interval sits" subtitle={`${u.interval_method} · segment ${String(unc.segment ?? "")}`} />
          <CardBody>
            <IntervalBand
              lower={u.lower_bound}
              central={u.central_estimate}
              upper={u.upper_bound}
              uwi={u.underwriting_income_monthly}
              lowerBeforeAllowance={unc.lower_before_allowance as number | null}
            />
            <div className="mt-2 grid grid-cols-2 gap-x-6 gap-y-2 text-xs">
              <Chip label="Coverage risk" value={<Badge tone={riskTone(u.coverage_risk)}>{u.coverage_risk}</Badge>} />
              <Chip label="Legal attribution" value={<Badge tone={u.legal_attribution_status === "ATTRIBUTABLE" ? "good" : "warn"}>{u.legal_attribution_status}</Badge>} />
              <Chip label="Archetype" value={`${r.archetype?.code} ${meta?.archetypes[r.archetype?.code ?? ""] ?? ""}`} />
              <Chip label="Cycle" value={String(r.cycle?.status ?? "—")} />
              <Chip label="Trend regime" value={String(r.trend?.regime ?? "—")} />
              <Chip label="Role uncertainty" value={pct(r.role_uncertainty)} />
            </div>
          </CardBody>
        </Card>
      </div>

      {/* What the engine learned */}
      <div>
        <div className="mb-3 flex items-baseline justify-between">
          <h3 className="text-sm font-semibold text-ink-100">What the engine learned</h3>
          <button onClick={() => onView("story")} className="inline-flex items-center gap-1 text-xs text-sky-300 hover:text-sky-200">
            Full business story, daily calendar and counterparty network <ArrowRight className="h-3 w-3" />
          </button>
        </div>
        <StoryCards trace={trace} meta={meta} limit={4} />
      </div>

      {/* Bridge */}
      <Card>
        <CardHeader
          title="Economic bridge: gross credits to underwriting income (monthly equivalent)"
          subtitle={String(eo.basis ?? "")}
          right={
            <div className="flex items-center gap-3">
              <Tabs
                tabs={[
                  { id: "flow", label: "Money flow" },
                  { id: "waterfall", label: "Waterfall" },
                ]}
                value={bridgeView}
                onChange={setBridgeView}
              />
              <button onClick={() => onView("AUDIT")} className="hidden items-center gap-1 text-xs text-sky-300 hover:text-sky-200 md:inline-flex">
                Explainability detail <ArrowRight className="h-3 w-3" />
              </button>
            </div>
          }
        />
        <CardBody>
          {bridgeView === "flow" ? (
            <MoneyFlow bridge={r.bridge ?? []} />
          ) : (
            <>
              <Legend
                items={[
                  { label: "Total", color: "#94a1b6" },
                  { label: "Deduction", color: "#fb7185" },
                  { label: "Subtotal", color: "#38bdf8" },
                  { label: "Adjustment", color: "#fbbf24" },
                  { label: "SBCI", color: "#34d399" },
                  { label: "UWI (policy)", color: "#a78bfa" },
                ]}
              />
              <BridgeWaterfall bridge={r.bridge ?? []} />
            </>
          )}
          <div className="mt-4 grid gap-x-8 md:grid-cols-2">
            {(r.bridge ?? []).map((b) => (
              <div key={b.line} className="flex items-baseline justify-between gap-3 border-b border-white/[0.04] py-1.5 text-xs">
                <span className={b.kind === "SUBTOTAL" || b.kind === "RESULT" || b.kind === "POLICY" ? "font-semibold text-ink-100" : "text-ink-300"}>
                  {b.line}
                  {b.note && <span className="ml-2 text-[11px] text-ink-400">{b.note}</span>}
                </span>
                <span className="font-mono text-ink-100 tabular">{inr(b.monthly_amount, 2)}</span>
              </div>
            ))}
          </div>
        </CardBody>
      </Card>

      {policy && <PolicyLab trace={trace} policy={policy} />}

      <div className="grid gap-6 xl:grid-cols-[1.6fr_1fr]">
        <Card>
          <CardHeader title="Monthly operating cash" subtitle="EOC (expected operating collections) − COR (core operating requirement) = ROC; CAOCG is ROC after cycle normalisation" />
          <CardBody>
            <Legend
              items={[
                { label: "EOC", color: "#34d399" },
                { label: "COR", color: "#fb7185" },
                { label: "ROC", color: "#38bdf8" },
                { label: "CAOCG", color: "#fbbf24", dashed: true },
              ]}
            />
            <SeriesChart
              data={r.monthly_series ?? []}
              xKey="month"
              series={[
                { key: "eoc", label: "EOC", color: "#34d399", type: "bar" },
                { key: "cor", label: "COR", color: "#fb7185", type: "bar" },
                { key: "roc", label: "ROC", color: "#38bdf8", type: "line" },
                { key: "caocg", label: "CAOCG", color: "#fbbf24", type: "line", dashed: true },
              ]}
              referenceY={[{ y: u.central_estimate, label: "SBCI", color: "#34d399" }]}
            />
          </CardBody>
        </Card>
        <Card>
          <CardHeader
            title="Confidence dimensions"
            subtitle={`Weighted geometric mean = ${pct(u.confidence)}`}
            right={
              <button onClick={() => onView("M8")} className="inline-flex items-center gap-1 text-xs text-sky-300 hover:text-sky-200">
                M8 Uncertainty model <ArrowRight className="h-3 w-3" />
              </button>
            }
          />
          <CardBody>
            <ConfidenceRadar dims={r.confidence_dimensions ?? {}} height={260} />
            <div className="grid grid-cols-2 gap-x-4 text-[11px]">
              {Object.entries(r.confidence_dimensions ?? {}).map(([k, v]) => (
                <div key={k} className="flex justify-between border-b border-white/[0.04] py-1">
                  <span className="text-ink-300">
                    <span className="font-mono text-ink-400">{k.slice(0, 4)}</span> {featureName(k).label}
                  </span>
                  <span className="font-mono text-ink-100 tabular">{v.toFixed(2)}</span>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader title="Reason codes and flags" subtitle="Section 28.2 reason codes fire on thresholds; flags are engine notes" />
          <CardBody className="space-y-3">
            {r.reasons.length === 0 && <div className="text-xs text-emerald-300">No reason codes fired.</div>}
            {r.reasons.map((rc) => (
              <div key={rc.code} className="rounded-xl border border-amber-400/20 bg-amber-400/[0.05] px-4 py-3">
                <div className="flex items-center gap-2 text-sm">
                  <span className="font-mono text-xs font-semibold text-amber-300">{rc.code}</span>
                  <span className="font-semibold text-ink-100">{rc.reason}</span>
                </div>
                <div className="mt-1 text-xs text-ink-300">{rc.meaning}</div>
                <div className="mt-1 font-mono text-[11px] text-ink-400">
                  {Object.entries(rc.evidence).map(([k, v]) => `${k}=${typeof v === "number" ? v.toFixed(4) : JSON.stringify(v)}`).join("  ")}
                </div>
              </div>
            ))}
            <ul className="space-y-1.5">
              {r.flags.map((f) => (
                <li key={f} className="flex items-start gap-2 text-xs text-ink-300">
                  <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-400" /> {f}
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Component flow and timing"
            subtitle={`End to end ${ms(trace.totalMs)} for ${r.transaction_count?.toLocaleString("en-IN")} transactions · timed per pipeline step; components in one step share its time`}
          />
          <CardBody className="space-y-2.5">
            {steps.map((s) => {
              const d = trace.steps[s.id];
              const inStep = componentsInStep(meta, s.id);
              return (
                <div key={s.id} className="grid grid-cols-[minmax(0,15rem)_1fr_4rem] items-center gap-3 text-xs">
                  <span className="flex flex-wrap items-center gap-1">
                    {inStep.map((c) => (
                      <button key={c.id} onClick={() => onView(c.id)} className="group inline-flex items-center gap-1 rounded-md pr-1 hover:bg-white/[0.04]" title={c.responsibility}>
                        <ComponentChip c={c} />
                        <span className="truncate text-ink-200 group-hover:text-sky-200">{c.name}</span>
                      </button>
                    ))}
                  </span>
                  <span className="h-1.5 overflow-hidden rounded-full bg-white/[0.05]" title={s.id}>
                    <span className="block h-full rounded-full bg-gradient-to-r from-sky-400 to-violet-400" style={{ width: `${((d?.compute_ms ?? 0) / maxMs) * 100}%` }} />
                  </span>
                  <span className="text-right font-mono text-ink-300 tabular">{ms(d?.compute_ms)}</span>
                </div>
              );
            })}
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader title="Transactions that moved the result most" subtitle="Click a row to follow that transaction through M1 → M4 and the economic ledger" />
        <CardBody className="grid gap-6 lg:grid-cols-2">
          {Object.entries(r.transaction_evidence ?? {}).map(([group, list]) => (
            <div key={group}>
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-ink-400">{group.replace(/_/g, " ")}</div>
              {list.length === 0 && <div className="text-xs text-ink-400">None</div>}
              <div className="space-y-1">
                {list.map((t) => (
                  <button
                    key={t.transaction_id}
                    onClick={() => onOpenTxn(t.transaction_id)}
                    className="grid w-full grid-cols-[5.5rem_1fr_auto] items-center gap-3 rounded-lg px-2 py-1.5 text-left text-xs hover:bg-white/[0.04]"
                  >
                    <span className="text-ink-400 tabular">{t.date}</span>
                    <span className="truncate text-ink-200">
                      <span className="mr-2 font-mono text-ink-300">{t.top_role}</span>
                      {String(trace.txns.get(t.transaction_id)?.normalized_narration ?? t.transaction_id)}
                    </span>
                    <span className="font-mono text-ink-100 tabular">{inr(t.amount)}</span>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </CardBody>
      </Card>
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-ink-400">{label}</div>
      <div className="mt-0.5 font-mono text-sm font-medium text-ink-100 tabular">{value}</div>
    </div>
  );
}

function Chip({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2 border-b border-white/[0.04] py-1.5">
      <span className="text-ink-400">{label}</span>
      <span className="text-ink-100">{value}</span>
    </div>
  );
}
