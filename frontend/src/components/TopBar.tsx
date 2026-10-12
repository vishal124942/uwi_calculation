"use client";

import { FileSpreadsheet, FlaskConical } from "lucide-react";
import { inr, ms } from "@/lib/format";
import type { TraceState } from "@/lib/trace";
import { CountUp } from "./motion";
import { Badge, statusTone } from "./ui";

export default function TopBar({ trace }: { trace: TraceState }) {
  const req = trace.request;
  const result = trace.result;
  const uwi = result?.underwriting?.underwriting_income_monthly;
  return (
    <header className="sticky top-0 z-20 border-b border-white/[0.06] bg-ink-950/80 backdrop-blur-xl">
      <div className="mx-auto flex max-w-[1480px] flex-wrap items-center gap-x-6 gap-y-2 px-6 py-3 lg:px-8">
        <div className="flex min-w-0 items-center gap-2.5">
          {trace.source === "demo" ? <FlaskConical className="h-4 w-4 text-violet-300" /> : <FileSpreadsheet className="h-4 w-4 text-sky-300" />}
          <div className="min-w-0">
            <div className="truncate text-sm font-medium">
              {req ? req.accounts.map((a) => a.source_file ?? a.account_id).join(" + ") : "Starting…"}
            </div>
            {req && (
              <div className="truncate text-[11px] text-ink-400">
                {req.accounts.length} account{req.accounts.length > 1 ? "s" : ""} ·{" "}
                {req.accounts.reduce((n, a) => n + a.transactions, 0).toLocaleString("en-IN")} transactions ·{" "}
                {req.accounts[0]?.statement_start} → {req.accounts[0]?.statement_end} · as of {req.as_of_date} · {req.legal_owner_type}
              </div>
            )}
          </div>
        </div>
        <div className="ml-auto flex items-center gap-3">
          {trace.status === "running" && <Badge tone="info">Running…</Badge>}
          {trace.status === "error" && <Badge tone="bad">Error</Badge>}
          {result && <Badge tone={statusTone(result.status)}>{result.status}</Badge>}
          {uwi !== undefined && uwi !== null && (
            <div className="text-right">
              <div className="text-[10px] uppercase tracking-wider text-ink-400">UWI / month</div>
              <div className="font-mono text-base font-semibold text-policy tabular">
                <CountUp value={uwi} format={(v) => inr(v)} />
              </div>
            </div>
          )}
          {trace.totalMs !== undefined && <span className="text-[11px] text-ink-400 tabular">{ms(trace.totalMs)}</span>}
        </div>
      </div>
    </header>
  );
}
