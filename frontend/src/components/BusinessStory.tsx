"use client";

import {
  ArrowRight,
  CalendarDays,
  Landmark,
  Network,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  ShoppingCart,
  Store,
  TrendingDown,
  TrendingUp,
  Users,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import { type ReactNode, useMemo } from "react";
import { counterparties, dailyFlows, riskSignals, type Counterparty } from "@/lib/insights";
import { inr, inrShort, num, pct } from "@/lib/format";
import type { TraceState } from "@/lib/trace";
import type { Meta } from "@/lib/types";
import CalendarHeatmap from "./CalendarHeatmap";
import CounterpartyNetwork from "./CounterpartyNetwork";
import type { View } from "./Sidebar";
import { Card, CardBody, CardHeader } from "./ui";

const OUTFLOW_LABEL: Record<string, string> = {
  direct_cost: "Stock and purchases",
  payroll: "Staff and labour",
  rent: "Rent",
  utilities: "Utilities",
  logistics: "Logistics",
  other_opex: "Other running costs",
  statutory: "Taxes and statutory",
  debt_interest: "Loan interest",
  debt_principal: "Loan principal",
  capex: "Capital spend",
  maintenance_capex: "Maintenance capex",
  owner_draw: "Owner's drawings",
  personal_expense: "Personal spending",
  internal_out: "Own-account transfers",
  refund_out: "Refunds",
  business_cash_withdrawal: "Cash withdrawals",
  pass_through_out: "Pass-through",
  bank_fee: "Bank fees",
  unknown_out: "Unexplained",
};
const OUTFLOW_COLOURS = ["#fb7185", "#f97316", "#fbbf24", "#a78bfa", "#38bdf8", "#64748b"];

type Tone = "emerald" | "sky" | "violet" | "amber" | "rose";
const TONE: Record<Tone, string> = {
  emerald: "from-emerald-400/25 to-emerald-400/5 text-emerald-200 ring-emerald-400/30",
  sky: "from-sky-400/25 to-sky-400/5 text-sky-200 ring-sky-400/30",
  violet: "from-violet-400/25 to-violet-400/5 text-violet-200 ring-violet-400/30",
  amber: "from-amber-400/25 to-amber-400/5 text-amber-200 ring-amber-400/30",
  rose: "from-rose-400/25 to-rose-400/5 text-rose-200 ring-rose-400/30",
};

interface Story {
  id: string;
  icon: LucideIcon;
  tone: Tone;
  label: string;
  headline: string;
  body: ReactNode;
  visual?: ReactNode;
}

function Sparkline({ values, colour }: { values: number[]; colour: string }) {
  if (values.length < 2) return null;
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 1);
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * 100},${28 - ((v - min) / (max - min || 1)) * 26}`).join(" ");
  return (
    <svg viewBox="0 0 100 30" preserveAspectRatio="none" className="h-8 w-full">
      <polyline points={`0,30 ${pts} 100,30`} fill={colour} fillOpacity={0.12} stroke="none" />
      <polyline points={pts} fill="none" stroke={colour} strokeWidth={1.6} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function MiniBars({ items }: { items: { label: string; value: number; colour: string }[] }) {
  const max = Math.max(...items.map((i) => i.value), 1e-9);
  return (
    <div className="space-y-1.5">
      {items.map((i) => (
        <div key={i.label} className="grid grid-cols-[minmax(0,1fr)_3rem] items-center gap-2 text-[11px]">
          <div className="min-w-0">
            <div className="truncate text-ink-300">{i.label}</div>
            <div className="mt-0.5 h-1 rounded-full bg-white/[0.05]">
              <div className="h-full rounded-full transition-all duration-700" style={{ width: `${(i.value / max) * 100}%`, background: i.colour }} />
            </div>
          </div>
          <span className="text-right font-mono text-ink-200 tabular">{pct(i.value, i.value < 0.1 ? 1 : 0)}</span>
        </div>
      ))}
    </div>
  );
}

function StackBar({ items }: { items: { label: string; value: number; colour: string }[] }) {
  return (
    <div>
      <div className="flex h-2 overflow-hidden rounded-full">
        {items.map((i) => (
          <div key={i.label} style={{ width: `${i.value * 100}%`, background: i.colour }} title={`${i.label} ${pct(i.value)}`} />
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[10.5px] text-ink-300">
        {items.slice(0, 4).map((i) => (
          <span key={i.label} className="inline-flex items-center gap-1">
            <span className="h-1.5 w-1.5 rounded-full" style={{ background: i.colour }} />
            {i.label} {pct(i.value, 0)}
          </span>
        ))}
      </div>
    </div>
  );
}

function buildStories(trace: TraceState, meta: Meta | null, parties: Counterparty[]): Story[] {
  const r = trace.result!;
  const u = r.underwriting!;
  const sig = riskSignals(trace);
  const name = (code: string) => meta?.archetypes[code] ?? code;
  const stories: Story[] = [];

  const probs = Object.entries(r.archetype?.probabilities ?? {}).sort((a, b) => b[1] - a[1]);
  const code = r.archetype?.code ?? "";
  const unclassified = name(code) === "Unclassified";
  stories.push({
    id: "archetype",
    icon: Store,
    tone: "violet",
    label: "What kind of business",
    headline: unclassified ? "Not confidently classified" : name(code),
    body: unclassified ? (
      <>Closest match is <b className="text-ink-100">{name(probs[0]?.[0] ?? "")}</b> at {pct(probs[0]?.[1])}, not likely enough for M5 to commit.</>
    ) : (
      <>M5 is {pct(r.archetype?.probability)} sure; next most likely is {name(probs[1]?.[0] ?? "")}.</>
    ),
    visual: <MiniBars items={probs.slice(0, 3).map(([c, p], i) => ({ label: name(c), value: p, colour: ["#a78bfa", "#38bdf8", "#64748b"][i] }))} />,
  });

  const payers = parties.filter((p) => p.credit > 0).sort((a, b) => b.credit - a.credit);
  const totalIn = payers.reduce((n, p) => n + p.credit, 0);
  const top5 = totalIn ? payers.slice(0, 5).reduce((n, p) => n + p.credit, 0) / totalIn : 0;
  stories.push({
    id: "payers",
    icon: Users,
    tone: "emerald",
    label: "Who pays the business",
    headline: `${payers.length.toLocaleString("en-IN")} paying counterparties`,
    body: (
      <>
        The top 5 bring {pct(top5)} of money in: {top5 < 0.3 ? "a broad, diversified customer base." : top5 < 0.6 ? "moderately concentrated." : "highly concentrated on a few payers."}
      </>
    ),
    visual: <MiniBars items={payers.slice(0, 3).map((p, i) => ({ label: p.name, value: totalIn ? p.credit / totalIn : 0, colour: ["#34d399", "#2dd4bf", "#a3e635"][i] }))} />,
  });

  const mix = r.role_mix_full_period ?? {};
  const outflows = Object.entries(mix)
    .filter(([k]) => k in OUTFLOW_LABEL)
    .sort((a, b) => b[1] - a[1]);
  const totalOut = outflows.reduce((n, [, v]) => n + v, 0);
  const shares = outflows.slice(0, 5).map(([k, v], i) => ({ label: OUTFLOW_LABEL[k], value: totalOut ? v / totalOut : 0, colour: OUTFLOW_COLOURS[i] }));
  const rest = 1 - shares.reduce((n, s) => n + s.value, 0);
  if (rest > 0.001) shares.push({ label: "Everything else", value: rest, colour: OUTFLOW_COLOURS[5] });
  stories.push({
    id: "spend",
    icon: ShoppingCart,
    tone: "rose",
    label: "Where the money goes",
    headline: shares[0] ? `${shares[0].label}: ${pct(shares[0].value, 0)}` : "No outflows",
    body: <>Of {inrShort(totalOut)} going out each month, by the role M2/M3 assigned to each payment.</>,
    visual: <StackBar items={shares} />,
  });

  const cyc = sig.s13_cycle ?? {};
  const lag = num(cyc.WC01_PeakOutflowToInflowLag);
  const conversion = num(r.cycle?.conversion_ratio);
  const identified = cyc.status === "IDENTIFIED";
  stories.push({
    id: "cycle",
    icon: RefreshCw,
    tone: "sky",
    label: "Cash cycle",
    headline: !identified ? "No reliable purchase cycle" : lag ? `Purchases return in ~${lag} days` : "Buys and sells in the same week",
    body: identified ? (
      <>
        {conversion ? <>Every ₹1 of purchases comes back as <b className="text-ink-100">₹{conversion.toFixed(2)}</b> of collections. </> : null}
        Cycle normalisation moved monthly income by {inr(r.bridge?.find((b) => b.line.startsWith("Cycle"))?.monthly_amount ?? 0)}.
      </>
    ) : (
      <>M6 found no stable lag between purchases and collections, so income is not cycle-adjusted.</>
    ),
  });

  const roc = (r.monthly_series ?? []).map((m) => m.roc);
  const tr = sig.s18_trend ?? {};
  const ratio = num(tr.TR03_ROC_3m_vs_12m);
  const up = ratio !== null && ratio >= 1;
  stories.push({
    id: "trend",
    icon: up ? TrendingUp : TrendingDown,
    tone: up ? "emerald" : "amber",
    label: "Momentum",
    headline: `${String(tr.regime ?? "—").replace(/_/g, " ").toLowerCase().replace(/^./, (c) => c.toUpperCase())}${ratio !== null ? `, ${up ? "+" : "−"}${pct(Math.abs(ratio - 1), 0)}` : ""}`,
    body: <>Last 3 months of cash generation against the 12-month average; {pct(num(tr.TR06_PositiveROCMonthRatio), 0)} of months were cash-positive.</>,
    visual: <Sparkline values={roc} colour={up ? "#34d399" : "#fbbf24"} />,
  });

  const own = sig.s16_owner ?? {};
  const liq = sig.s14_liquidity ?? {};
  const draw = num(own.owner_draw_monthly) ?? 0;
  stories.push({
    id: "owner",
    icon: Wallet,
    tone: "violet",
    label: "Owner and cushion",
    headline: draw ? `Owner takes ${inr(draw)} / month` : "No regular owner drawings",
    body: (
      <>
        {draw ? <>{pct(draw / (u.central_estimate || 1), 0)} of sustainable income. </> : null}
        Balance averages {inrShort(liq.BAL01_AverageDailyBalance)} and never dropped below {inrShort(liq.BAL04_MinimumBalance)}.
      </>
    ),
  });

  const fin = sig.s15_financing ?? {};
  const debt = num(fin.debt_service_monthly) ?? 0;
  stories.push({
    id: "debt",
    icon: Landmark,
    tone: debt > 0.2 * u.central_estimate ? "amber" : "sky",
    label: "Borrowing",
    headline: debt < 1 ? "No visible loan repayments" : `Debt service ${inr(debt)} / month`,
    body: (
      <>
        {pct(debt / (u.central_estimate || 1), 1)} of sustainable income; financing is {pct(num(fin.FIN01_FinancingCreditRatio), 2)} of credits. Post-debt free cash{" "}
        {inr(r.economic_outputs?.post_debt_free_cash_monthly)}.
      </>
    ),
  });

  const anomaly = sig.s19_anomaly ?? {};
  const issues = [
    ...(u.coverage_risk !== "LOW" ? [`coverage risk ${u.coverage_risk}`] : []),
    ...(anomaly.review_required ? ["anomaly review required"] : []),
    ...r.reasons.map((x) => `${x.code} ${x.reason}`),
    ...u.referral_reasons,
  ];
  stories.push({
    id: "flags",
    icon: issues.length ? ShieldAlert : ShieldCheck,
    tone: issues.length ? "amber" : "emerald",
    label: "Things to check",
    headline: issues.length ? `${issues.length} point${issues.length > 1 ? "s" : ""} to review` : "No red flags",
    body: issues.length ? (
      <ul className="list-disc space-y-0.5 pl-4">
        {issues.slice(0, 3).map((i) => <li key={i}>{i}</li>)}
      </ul>
    ) : (
      <>Coverage risk {u.coverage_risk.toLowerCase()}, no anomaly triggers and no reason codes fired.</>
    ),
  });
  return stories;
}

function StoryCard({ s, index }: { s: Story; index: number }) {
  const Icon = s.icon;
  return (
    <div
      className="spotlight rise relative flex flex-col rounded-2xl border border-white/[0.07] bg-ink-900/70 p-4 transition-colors hover:border-white/15"
      style={{ animationDelay: `${index * 60}ms` }}
    >
      <div className="flex items-center gap-2.5">
        <span className={`flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br ring-1 ring-inset ${TONE[s.tone]}`}>
          <Icon className="h-4 w-4" />
        </span>
        <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-400">{s.label}</span>
      </div>
      <div className="mt-3 text-[17px] font-semibold leading-snug tracking-tight text-ink-100">{s.headline}</div>
      <div className="mt-1.5 text-xs leading-relaxed text-ink-300">{s.body}</div>
      {s.visual && <div className="mt-auto pt-3">{s.visual}</div>}
    </div>
  );
}

export function StoryCards({ trace, meta, limit }: { trace: TraceState; meta: Meta | null; limit?: number }) {
  const parties = useMemo(() => counterparties(trace), [trace]);
  const stories = useMemo(() => buildStories(trace, meta, parties), [trace, meta, parties]);
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {stories.slice(0, limit).map((s, i) => <StoryCard key={s.id} s={s} index={i} />)}
    </div>
  );
}

export default function BusinessStory({
  trace,
  meta,
  onOpenTxn,
  onView,
}: {
  trace: TraceState;
  meta: Meta | null;
  onOpenTxn: (id: string) => void;
  onView: (v: View) => void;
}) {
  const days = useMemo(() => dailyFlows(trace), [trace]);
  const parties = useMemo(() => counterparties(trace), [trace]);
  return (
    <div className="space-y-6">
      <div>
        <div className="text-xs font-semibold uppercase tracking-[0.2em] text-violet-300/80">Business story</div>
        <h2 className="mt-2 text-3xl font-semibold tracking-tight">What the engine learned about this business</h2>
        <p className="mt-1 max-w-3xl text-sm text-ink-300">
          Plain-language findings drawn from the same run: archetype (M5), counterparties (M2), roles (M2/M3), cycle (M6), trend, liquidity and risk signals.
        </p>
      </div>

      <StoryCards trace={trace} meta={meta} />

      <Card>
        <CardHeader
          title={
            <span className="inline-flex items-center gap-2">
              <CalendarDays className="h-4 w-4 text-emerald-300" /> Every day of the statement
            </span>
          }
          subtitle="Daily money in and out; hover a day for its totals"
        />
        <CardBody>
          <CalendarHeatmap days={days} />
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title={
            <span className="inline-flex items-center gap-2">
              <Network className="h-4 w-4 text-sky-300" /> Counterparty network
            </span>
          }
          subtitle="Line width is money; colour is the role M2/M3 assigned to most of that counterparty's money"
          right={
            <button onClick={() => onView("M2")} className="inline-flex items-center gap-1 text-xs text-sky-300 hover:text-sky-200">
              M2 entity resolution <ArrowRight className="h-3 w-3" />
            </button>
          }
        />
        <CardBody>
          <CounterpartyNetwork parties={parties} roles={meta?.roles} onOpenTxn={onOpenTxn} />
        </CardBody>
      </Card>
    </div>
  );
}
