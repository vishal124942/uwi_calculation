"use client";

import { CheckCircle2, OctagonX, TriangleAlert } from "lucide-react";
import { useMemo } from "react";
import { cellText, inr, pct } from "@/lib/format";
import { rowsOf } from "@/lib/trace";
import type { Cell, Row } from "@/lib/types";
import { Badge, CalcLine, Card, CardBody, CardHeader, Empty, Formula, Note } from "../ui";
import { TxnLink, useTxnRows, type StepProps } from "./shared";

type Params = Record<string, number>;

interface Check {
  key: string;
  label: string;
  value: (m: Row) => Cell;
  format: (v: Cell) => string;
  /** Hard-stop rule exactly as s04_statement_integrity_gate applies it; undefined = informational metric. */
  hardStop?: (m: Row, p: Params) => boolean;
  rule?: (p: Params) => string;
  stopCode?: string;
}

const months = (v: Cell) => (typeof v === "number" ? `${v.toFixed(2)} months` : "—");

const CHECKS: Check[] = [
  {
    key: "DQ01_StatementCoverageDays", label: "Statement coverage", value: (m) => m.DQ01_StatementCoverageDays, format: (v) => pct(v),
    hardStop: (m, p) => (m.DQ01_StatementCoverageDays as number) < p.min_statement_coverage,
    rule: (p) => `stop if < ${pct(p.min_statement_coverage, 0)} (gaps > ${p.long_gap_days} days are uncovered)`, stopCode: "STATEMENT_PERIOD_MATERIALLY_INCOMPLETE",
  },
  {
    key: "DQ02_TxnReconciliationPassRate", label: "Balance reconciliation pass rate", value: (m) => m.DQ02_TxnReconciliationPassRate, format: (v) => pct(v, 2),
    hardStop: (m, p) =>
      m.DQ02_TxnReconciliationPassRate !== null &&
      (m.DQ02_TxnReconciliationPassRate as number) < p.min_reconciliation_pass_rate &&
      (m.DQ09_BalanceBreakMagnitude as number) > p.max_balance_break_magnitude,
    rule: (p) => `stop if < ${pct(p.min_reconciliation_pass_rate, 0)} AND break magnitude > ${pct(p.max_balance_break_magnitude, 0)}`,
    stopCode: "UNRECONCILED_STATEMENT_ARITHMETIC",
  },
  { key: "DQ03_BalanceAvailability", label: "Rows with a running balance", value: (m) => m.DQ03_BalanceAvailability, format: (v) => pct(v) },
  { key: "DQ04_NarrationAvailability", label: "Rows with a narration", value: (m) => m.DQ04_NarrationAvailability, format: (v) => pct(v) },
  {
    key: "DQ05_DateOrderErrorRate", label: "Date-order errors", value: (m) => m.DQ05_DateOrderErrorRate, format: (v) => pct(v, 2),
    hardStop: (m, p) => (m.DQ05_DateOrderErrorRate as number) > p.max_date_order_error_rate,
    rule: (p) => `stop if > ${pct(p.max_date_order_error_rate, 0)}`, stopCode: "NON_DETERMINISTIC_ORDERING",
  },
  {
    key: "duplicate_amount_share", label: "Duplicate amount share (DQ06 rate shown as context)", value: (m) => m.duplicate_amount_share,
    format: (v) => pct(v, 2), hardStop: (m, p) => (m.duplicate_amount_share as number) > p.max_duplicate_amount_share,
    rule: (p) => `stop if > ${pct(p.max_duplicate_amount_share, 0)}`, stopCode: "DUPLICATE_OR_PARSE_CORRUPTION",
  },
  { key: "DQ07_ParseLowConfidenceRate", label: "Low parse-confidence rows", value: (m) => m.DQ07_ParseLowConfidenceRate, format: (v) => pct(v, 2) },
  {
    key: "DQ08_MissingAmountRate", label: "Rejected rows (missing amount/date)", value: (m) => m.DQ08_MissingAmountRate, format: (v) => pct(v, 2),
    hardStop: (m, p) => (m.DQ08_MissingAmountRate as number) > p.max_missing_amount_rate,
    rule: (p) => `stop if > ${pct(p.max_missing_amount_rate, 0)}`, stopCode: "MISSING_AMOUNTS",
  },
  { key: "DQ09_BalanceBreakMagnitude", label: "Break magnitude (Σ break error ÷ throughput)", value: (m) => m.DQ09_BalanceBreakMagnitude, format: (v) => pct(v, 3) },
  {
    key: "DQ10_HistoryMonths", label: "History covered", value: (m) => m.DQ10_HistoryMonths, format: months,
    hardStop: (m, p) => (m.DQ10_HistoryMonths as number) < p.min_history_months,
    rule: (p) => `INSUFFICIENT_HISTORY if < ${p.min_history_months} months (preferred ${p.preferred_history_months})`, stopCode: "HISTORY_BELOW_MINIMUM",
  },
  { key: "DQ11_LongGapCount", label: "Long gaps without transactions", value: (m) => m.DQ11_LongGapCount, format: (v) => cellText(v) },
  { key: "DQ12_SourceReliabilityClass", label: "Source reliability class", value: (m) => m.DQ12_SourceReliabilityClass, format: (v) => cellText(v) },
];

export default function Step02({ data, trace, onOpenTxn }: StepProps) {
  const metrics = rowsOf(data.tables.step02_dq_metrics);
  const params = (data.detail.parameters ?? {}) as Params;
  const rows = useTxnRows(trace);
  const breaks = useMemo(() => rows.filter((r) => r.s02_reconciliation_break === true), [rows]);
  const example = useMemo(() => {
    const i = rows.findIndex((r, k) => k > 0 && typeof r.s02_reconciliation_error === "number" && rows[k - 1].account_id === r.account_id);
    return i > 0 ? { prev: rows[i - 1], cur: rows[i] } : null;
  }, [rows]);

  return (
    <div className="space-y-6">
      {metrics.map((m) => {
        const hardStop = m.pipeline_hard_stop === true;
        return (
          <Card key={String(m.account_id)}>
            <CardHeader
              title={`Account ${m.account_id}: ${hardStop ? "hard stop" : "passed the gate"}`}
              subtitle={`${cellText(m.transaction_count)} transactions · throughput ${inr(m.throughput)}`}
              right={<Badge tone={hardStop ? "bad" : "good"}>{hardStop ? String(m.pipeline_status) : "PASSED"}</Badge>}
            />
            <CardBody>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {CHECKS.map((c) => {
                  const v = c.value(m);
                  const failed = c.hardStop && v !== null && v !== undefined ? c.hardStop(m, params) : false;
                  return (
                    <div key={c.key} className={`rounded-xl border px-4 py-3 ${failed ? "border-rose-400/30 bg-rose-400/[0.05]" : "border-white/[0.06] bg-white/[0.02]"}`}>
                      <div className="flex items-start justify-between gap-2">
                        <div className="text-[11px] text-ink-400">
                          <span className="font-mono">{c.key.split("_")[0]}</span> {c.label}
                        </div>
                        {c.hardStop ? (
                          failed ? <OctagonX className="h-4 w-4 shrink-0 text-rose-300" /> : <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-300" />
                        ) : null}
                      </div>
                      <div className="mt-1 font-mono text-lg font-semibold text-ink-100 tabular">{c.format(v)}</div>
                      {c.rule && params && <div className="mt-0.5 text-[11px] text-ink-400">{c.rule(params)}</div>}
                    </div>
                  );
                })}
              </div>
              {((m.hard_stop_reasons as string[]) ?? []).length + ((m.warnings as string[]) ?? []).length > 0 && (
                <div className="mt-4 space-y-1.5">
                  {((m.hard_stop_reasons as string[]) ?? []).map((r) => (
                    <div key={r} className="flex items-center gap-2 text-xs text-rose-200"><OctagonX className="h-3.5 w-3.5" /> {r}</div>
                  ))}
                  {((m.warnings as string[]) ?? []).map((w) => (
                    <div key={w} className="flex items-center gap-2 text-xs text-amber-200"><TriangleAlert className="h-3.5 w-3.5" /> {w}</div>
                  ))}
                </div>
              )}
            </CardBody>
          </Card>
        );
      })}

      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader title="Statement arithmetic (Section 4.1)" subtitle="Every row with a balance is checked against the previous row of the same account" />
          <CardBody className="space-y-4">
            <Formula>
              expected_balance_after[k] = balance_after[k−1] + credit[k] − debit[k]
              <br />
              break if |balance_after[k] − expected| &gt; ₹{params.reconciliation_tolerance}
            </Formula>
            {example && (
              <div className="rounded-xl bg-white/[0.02] px-4 py-2">
                <CalcLine label="previous balance_after" value={inr(example.prev.balance_after, 2)} />
                <CalcLine op={example.cur.direction === "CREDIT" ? "+" : "−"} label={`${String(example.cur.direction).toLowerCase()} ${String(example.cur.normalized_narration ?? "").slice(0, 32)}`} value={inr(example.cur.amount, 2)} />
                <CalcLine op="=" label="expected balance_after" value={inr((example.prev.balance_after as number) + (example.cur.direction === "CREDIT" ? 1 : -1) * (example.cur.amount as number), 2)} />
                <CalcLine label="statement balance_after" value={inr(example.cur.balance_after, 2)} />
                <CalcLine op="Δ" label="reconciliation error" value={inr(example.cur.s02_reconciliation_error, 2)} emphasis />
              </div>
            )}
            <Note>
              Pass rate = 1 − breaks ÷ eligible rows. A low pass rate only stops the pipeline when the broken rupee mass is also material
              (DQ09 above its limit); otherwise breaks are reported as a warning.
            </Note>
          </CardBody>
        </Card>
        <Card>
          <CardHeader title={`Balance breaks (${breaks.length})`} subtitle="Rows whose statement balance disagrees with the arithmetic" />
          <CardBody>
            {breaks.length === 0 ? (
              <Empty>No breaks: every running balance reconciles.</Empty>
            ) : (
              breaks.slice(0, 30).map((r) => (
                <TxnLink key={String(r.transaction_id)} row={r} onOpen={onOpenTxn}>
                  <span className="text-rose-200">error {inr(r.s02_reconciliation_error, 2)}</span> · {String(r.normalized_narration ?? "")}
                </TxnLink>
              ))
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
