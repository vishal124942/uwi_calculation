"use client";

import { AlertTriangle, ArrowRight, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { componentCode, componentHeadline, componentStatuses, componentTiming } from "@/lib/components";
import { inr, inrShort, ms, num } from "@/lib/format";
import { roleColor } from "@/lib/roles";
import { sectionsOf, type TraceState } from "@/lib/trace";
import type { Meta, Row } from "@/lib/types";
import { ComponentChip } from "./ComponentView";
import { CountUp } from "./motion";
import { StatusDot, type View } from "./Sidebar";
import { Card, cx } from "./ui";

const FEED_SIZE = 90;
const FEED_MS = 40;
const AUTO_CONTINUE_MS = 4500;

function Elapsed({ since }: { since?: number }) {
  const [now, setNow] = useState(() => performance.now());
  useEffect(() => {
    const id = setInterval(() => setNow(performance.now()), 100);
    return () => clearInterval(id);
  }, []);
  return <span className="tabular">{since ? ms(now - since) : ""}</span>;
}

function Counter({ label, value, format, accent }: { label: string; value: number | null; format: (n: number) => string; accent: string }) {
  return (
    <div className={cx("rounded-xl border px-4 py-3 transition-colors duration-500", value === null ? "border-white/[0.05] bg-transparent" : "border-white/[0.08] bg-ink-900/70")}>
      <div className="text-[10.5px] font-medium uppercase tracking-wider text-ink-400">{label}</div>
      <div className={cx("mt-1 text-xl font-semibold tracking-tight", value === null ? "text-ink-600" : accent)}>
        {value === null ? "—" : <CountUp value={value} format={format} />}
      </div>
    </div>
  );
}

/** Transactions scroll past as the engine reads them; role chips appear once M2/M3 have classified them. */
function LiveFeed({ rows, total }: { rows: Row[]; total: number }) {
  const [shown, setShown] = useState(0);
  useEffect(() => {
    if (!rows.length) return;
    const id = setInterval(() => setShown((n) => (n >= rows.length ? n : n + 1)), FEED_MS);
    return () => clearInterval(id);
  }, [rows.length]);
  const visible = rows.slice(Math.max(0, shown - 11), shown).reverse();
  return (
    <div className="flex h-full flex-col rounded-2xl border border-white/[0.07] bg-ink-950/70">
      <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-2.5">
        <span className="inline-flex items-center gap-2 text-xs font-semibold text-ink-200">
          <span className="relative flex h-2 w-2">
            <span className={cx("absolute inline-flex h-full w-full rounded-full bg-emerald-400", shown < rows.length && "animate-ping opacity-60")} />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
          </span>
          Live feed
        </span>
        <span className="font-mono text-[11px] text-ink-400 tabular">
          {rows.length ? `${Math.round((shown / rows.length) * total).toLocaleString("en-IN")} / ${total.toLocaleString("en-IN")}` : "waiting for M1"}
        </span>
      </div>
      <div className="relative min-h-[22rem] flex-1 overflow-hidden px-2 py-2 font-mono text-[11px]">
        {visible.map((r) => {
          const credit = String(r.direction ?? "").toUpperCase().startsWith("C");
          const role = (r.s05_top_role ?? r.s04_top_role) as string | undefined;
          return (
            <div key={String(r.transaction_id)} className="ticker-in grid grid-cols-[5.2rem_1fr_auto_3.2rem] items-center gap-2 rounded-md px-2 py-1 odd:bg-white/[0.015]">
              <span className="text-ink-500 tabular">{String(r.booking_date)}</span>
              <span className="truncate text-ink-300">{String(r.normalized_narration ?? r.raw_narration ?? "")}</span>
              <span className={cx("tabular", credit ? "text-emerald-300" : "text-rose-300")}>
                {credit ? "+" : "−"}
                {inr(r.amount)}
              </span>
              <span className="text-right">
                {role ? (
                  <span className="pop rounded px-1 py-px text-[10px] font-semibold" style={{ color: roleColor(role), background: `${roleColor(role)}1f` }}>
                    {role}
                  </span>
                ) : (
                  <span className="text-[10px] text-ink-600">{String(r.s01_channel_family ?? "")}</span>
                )}
              </span>
            </div>
          );
        })}
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-ink-950 to-transparent" />
      </div>
    </div>
  );
}

export default function LiveRun({
  trace,
  meta,
  onView,
  onRestart,
  onContinue,
}: {
  trace: TraceState;
  meta: Meta | null;
  onView: (v: View) => void;
  onRestart: () => void;
  onContinue: () => void;
}) {
  const statuses = componentStatuses(meta, trace);
  const components = meta?.components ?? [];
  const failedDq = trace.status === "done" && !trace.result?.underwriting;
  const succeeded = trace.status === "done" && !!trace.result?.underwriting;
  const [stay, setStay] = useState(false);
  const doneCount = components.filter((c) => statuses[c.id] === "done").length;
  const progress = components.length ? doneCount / components.length : 0;

  useEffect(() => {
    if (!succeeded || stay) return;
    const t = setTimeout(onContinue, AUTO_CONTINUE_MS);
    return () => clearTimeout(t);
  }, [succeeded, stay, onContinue]);

  const s1 = trace.steps.step01_ingest_and_clean;
  const counts = useMemo(() => {
    const d = s1?.transactions;
    let credits: number | null = null;
    let debits: number | null = null;
    if (d) {
      const iDir = d.columns.indexOf("direction");
      const iAmt = d.columns.indexOf("amount");
      credits = 0;
      debits = 0;
      for (const row of d.rows) {
        const a = num(row[iAmt]) ?? 0;
        if (String(row[iDir]).toUpperCase().startsWith("C")) credits += a;
        else debits += a;
      }
    }
    const kv = (step: string, table: string) => sectionsOf(trace.steps[step]?.tables[table]);
    return {
      txns: d ? d.rows.length : null,
      credits,
      debits,
      entities: trace.steps.step03_transaction_evidence?.tables.step03_entities?.rows.length ?? null,
      roles: trace.steps.step04_role_inference?.transactions?.rows.length ?? null,
      pairs: trace.steps.step05_pairing_and_multi_account?.tables.step05_pair_edges?.rows.length ?? null,
      sbci: num(kv("step08_income_and_legal_attribution", "step08_sbci_and_legal").s21_sbci?.sbci_monthly),
      uwi: num(kv("step09_uncertainty_and_policy", "step09_uncertainty_and_policy").s21_policy_decision?.underwriting_income_monthly),
    };
  }, [s1, trace.steps]);

  const feedRows = useMemo(() => {
    if (!s1 || !trace.order.length) return [];
    const step = Math.max(1, Math.floor(trace.order.length / FEED_SIZE));
    const out: Row[] = [];
    for (let i = 0; i < trace.order.length && out.length < FEED_SIZE; i += step) {
      const row = trace.txns.get(trace.order[i]);
      if (row) out.push(row);
    }
    return out;
    // rows are the live objects in trace.txns, so later steps' role columns show up in place
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [s1]);

  return (
    <div className="mx-auto max-w-6xl space-y-6 pt-2">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">
            {trace.status === "running" ? "Reading the statement…" : trace.status === "error" ? "The run stopped" : failedDq ? "Stopped at the data-quality gate" : "Run finished"}
          </h2>
          <p className="mt-1 text-sm text-ink-300">
            Each component reports back the moment it finishes; click a finished one to inspect its calculations.
            {trace.status === "running" && (
              <span className="ml-2 text-ink-400">
                Elapsed <Elapsed since={trace.startedAt} />
              </span>
            )}
            {trace.totalMs !== undefined && <span className="ml-2 text-ink-400">Engine time {ms(trace.totalMs)}</span>}
          </p>
        </div>
        <div className="text-right font-mono text-sm text-ink-300 tabular">
          {doneCount} / {components.length} components
        </div>
      </div>

      {/* Progress rail */}
      <div className="relative px-1 pt-1">
        <div className="absolute left-4 right-4 top-[1.15rem] h-1 overflow-hidden rounded-full bg-white/[0.06]">
          <div className="relative h-full rounded-full bg-gradient-to-r from-sky-400 via-violet-400 to-emerald-400 transition-[width] duration-500 ease-out" style={{ width: `${progress * 100}%` }}>
            {trace.status === "running" && <div className="shimmer absolute inset-0" />}
          </div>
        </div>
        <ol className="relative grid" style={{ gridTemplateColumns: `repeat(${components.length || 1}, minmax(0, 1fr))` }}>
          {components.map((c) => {
            const status = statuses[c.id];
            return (
              <li key={c.id} className="flex flex-col items-center">
                <button
                  disabled={status !== "done"}
                  onClick={() => onView(c.id)}
                  title={`${c.name}: ${c.responsibility}`}
                  className={cx(
                    "flex h-9 w-9 items-center justify-center rounded-full border text-[9.5px] font-bold transition duration-300",
                    status === "done" && "pop border-emerald-400/40 bg-emerald-400/15 text-emerald-200 hover:scale-110",
                    status === "running" && "pulse-ring border-sky-400/60 bg-sky-400/20 text-sky-100",
                    status === "pending" && "border-white/10 bg-ink-900 text-ink-500",
                    status === "skipped" && "border-rose-400/25 bg-rose-400/10 text-rose-300",
                  )}
                >
                  {componentCode(c).replace("INPUT", "IN").replace("AUDIT", "AUD").replace("GATE", "DQ")}
                </button>
                <span className={cx("mt-1.5 hidden max-w-[5.5rem] text-center text-[10px] leading-tight md:block", status === "done" ? "text-ink-300" : "text-ink-500")}>{c.name}</span>
              </li>
            );
          })}
        </ol>
      </div>

      {/* Counters */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-8">
        <Counter label="Transactions" value={counts.txns} format={(n) => Math.round(n).toLocaleString("en-IN")} accent="text-ink-100" />
        <Counter label="Money in" value={counts.credits} format={inrShort} accent="text-emerald-300" />
        <Counter label="Money out" value={counts.debits} format={inrShort} accent="text-rose-300" />
        <Counter label="Counterparties" value={counts.entities} format={(n) => Math.round(n).toLocaleString("en-IN")} accent="text-sky-300" />
        <Counter label="Roles assigned" value={counts.roles} format={(n) => Math.round(n).toLocaleString("en-IN")} accent="text-violet-300" />
        <Counter label="Flow pairs" value={counts.pairs} format={(n) => Math.round(n).toLocaleString("en-IN")} accent="text-amber-300" />
        <Counter label="SBCI / month" value={counts.sbci} format={(n) => inr(n)} accent="text-emerald-300" />
        <Counter label="UWI / month" value={counts.uwi} format={(n) => inr(n)} accent="text-violet-200" />
      </div>

      {trace.status === "error" && (
        <Card className="border-rose-400/25 bg-rose-400/[0.05]">
          <div className="flex items-start gap-3 p-5">
            <AlertTriangle className="mt-0.5 h-5 w-5 text-rose-300" />
            <div className="flex-1">
              <div className="text-sm font-semibold text-rose-200">{trace.error}</div>
              <button onClick={onRestart} className="mt-3 rounded-lg border border-white/10 px-3 py-1.5 text-xs hover:bg-white/5">
                Back to start
              </button>
            </div>
          </div>
        </Card>
      )}

      {failedDq && (
        <Card className="border-amber-400/25 bg-amber-400/[0.05]">
          <div className="p-5 text-sm">
            <div className="font-semibold text-amber-200">Stopped at the data-quality gate: {trace.result?.status}</div>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-ink-200">
              {trace.result?.flags.map((f) => <li key={f}>{f}</li>)}
            </ul>
          </div>
        </Card>
      )}

      {succeeded && (
        <Card className="gradient-ring overflow-hidden">
          <div className="flex flex-wrap items-center gap-5 p-5">
            <Sparkles className="h-6 w-6 text-violet-300" />
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold text-ink-100">
                Underwriting income <span className="text-violet-200">{inr(trace.result?.underwriting?.underwriting_income_monthly)}</span> per month · {trace.result?.status}
              </div>
              <div className="mt-0.5 text-xs text-ink-400">{stay ? "Staying on the run screen." : "Opening the result overview…"}</div>
            </div>
            {!stay && (
              <button onClick={() => setStay(true)} className="rounded-lg px-3 py-1.5 text-xs text-ink-300 hover:bg-white/5 hover:text-ink-100">
                Stay here
              </button>
            )}
            <button
              onClick={onContinue}
              className="inline-flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-sky-400 to-violet-400 px-4 py-2 text-xs font-semibold text-ink-950 transition hover:brightness-110"
            >
              View results <ArrowRight className="h-3.5 w-3.5" />
            </button>
          </div>
          {!stay && (
            <div className="h-0.5 bg-white/[0.04]">
              <div className="h-full bg-gradient-to-r from-sky-400 to-violet-400" style={{ animation: `countdown ${AUTO_CONTINUE_MS}ms linear forwards` }} />
            </div>
          )}
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <ol className="space-y-2">
          {components.map((c) => {
            const status = statuses[c.id];
            const done = status === "done";
            return (
              <li key={c.id}>
                <button
                  disabled={!done}
                  onClick={() => onView(c.id)}
                  className={cx(
                    "group flex w-full items-start gap-3 rounded-xl border px-4 py-2.5 text-left transition duration-300",
                    status === "done" && "border-white/[0.08] bg-ink-900/70 hover:border-sky-400/30 hover:bg-ink-850",
                    status === "running" && "border-sky-400/30 bg-sky-400/[0.05]",
                    status === "pending" && "border-white/[0.04] bg-transparent opacity-45",
                    status === "skipped" && "border-white/[0.04] opacity-40",
                  )}
                >
                  <div className="pt-0.5">
                    <StatusDot status={status} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <ComponentChip c={c} />
                      <span className="text-[13px] font-semibold text-ink-100">{c.name}</span>
                    </div>
                    <div className="mt-0.5 truncate text-[11px] text-ink-300">
                      {done ? componentHeadline(c, trace) : status === "running" ? c.modules.map((m) => m.name).join(" → ") : status === "skipped" ? "Not run" : c.responsibility}
                    </div>
                  </div>
                  {done && (
                    <div className="flex items-center gap-2 text-[11px] text-ink-400">
                      <span className="tabular">{ms(componentTiming(meta, trace, c).ms)}</span>
                      <ArrowRight className="h-3.5 w-3.5 transition group-hover:translate-x-0.5 group-hover:text-sky-300" />
                    </div>
                  )}
                </button>
              </li>
            );
          })}
        </ol>
        <LiveFeed rows={feedRows} total={trace.order.length} />
      </div>
    </div>
  );
}
