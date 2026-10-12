"use client";

import { ExternalLink } from "lucide-react";
import { useMemo } from "react";
import { inr } from "@/lib/format";
import { transactionRows, type TraceState } from "@/lib/trace";
import type { Meta, Row, StepData } from "@/lib/types";

export interface StepProps {
  data: StepData;
  trace: TraceState;
  meta: Meta | null;
  onOpenTxn: (id: string) => void;
  /** Which component's slice of a shared pipeline step to render (see `PartView` in lib/components). */
  part?: string;
}

/** All transaction rows (cumulative columns), recomputed only when a step merges new columns. */
export function useTxnRows(trace: TraceState): Row[] {
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => transactionRows(trace), [trace.order, trace.txnVersion]);
}

export function groupBy<T>(items: T[], key: (t: T) => string): Map<string, T[]> {
  const out = new Map<string, T[]>();
  for (const it of items) {
    const k = key(it);
    const list = out.get(k);
    if (list) list.push(it);
    else out.set(k, [it]);
  }
  return out;
}

export function sum(rows: Row[], col: string): number {
  let s = 0;
  for (const r of rows) {
    const v = r[col];
    if (typeof v === "number") s += v;
  }
  return s;
}

export function TxnLink({ row, onOpen, children }: { row: Row; onOpen: (id: string) => void; children?: React.ReactNode }) {
  return (
    <button
      onClick={() => onOpen(String(row.transaction_id))}
      className="group grid w-full grid-cols-[5.5rem_1fr_auto_1rem] items-center gap-3 rounded-lg px-2 py-1.5 text-left text-xs hover:bg-white/[0.04]"
    >
      <span className="text-ink-400 tabular">{String(row.booking_date)}</span>
      <span className="truncate text-ink-200">{children ?? String(row.normalized_narration ?? row.raw_narration ?? "")}</span>
      <span className={`font-mono tabular ${row.direction === "CREDIT" ? "text-emerald-300" : "text-rose-300"}`}>
        {row.direction === "CREDIT" ? "+" : "−"}
        {inr(row.amount)}
      </span>
      <ExternalLink className="h-3 w-3 text-ink-500 group-hover:text-sky-300" />
    </button>
  );
}
