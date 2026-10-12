"use client";

import { useMemo } from "react";
import { inr, inrShort, pct } from "@/lib/format";
import { Legend, SeriesChart } from "../charts";
import { CalcLine, Card, CardBody, CardHeader, Formula, Note, Stat } from "../ui";
import { groupBy, sum, TxnLink, useTxnRows, type StepProps } from "./shared";

export default function Step01({ trace, onOpenTxn }: StepProps) {
  const rows = useTxnRows(trace);
  const stats = useMemo(() => {
    const credits = rows.filter((r) => r.direction === "CREDIT");
    const debits = rows.filter((r) => r.direction === "DEBIT");
    const channels = [...groupBy(rows, (r) => String(r.s01_channel_family ?? "UNKNOWN"))]
      .map(([channel, list]) => ({
        channel,
        count: list.length,
        credit: sum(list.filter((r) => r.direction === "CREDIT"), "amount"),
        debit: sum(list.filter((r) => r.direction === "DEBIT"), "amount"),
      }))
      .sort((a, b) => b.credit + b.debit - (a.credit + a.debit));
    const changed = rows.filter((r) => r.raw_narration && r.raw_narration !== r.normalized_narration).slice(0, 6);
    const lowConfidence = rows.filter((r) => typeof r.parse_confidence === "number" && r.parse_confidence < 0.6).length;
    return { credits, debits, channels, changed, lowConfidence };
  }, [rows]);

  const example = rows[0];
  const accounts = trace.request?.accounts ?? [];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Transactions" value={rows.length.toLocaleString("en-IN")} hint={`${accounts.length} account${accounts.length > 1 ? "s" : ""}`} />
        <Stat label="Credits" tone="income" value={inrShort(sum(stats.credits, "amount"))} hint={`${stats.credits.length.toLocaleString("en-IN")} transactions`} />
        <Stat label="Debits" tone="deduct" value={inrShort(sum(stats.debits, "amount"))} hint={`${stats.debits.length.toLocaleString("en-IN")} transactions`} />
        <Stat label="Low parse confidence" value={stats.lowConfidence} hint={`${pct(stats.lowConfidence / Math.max(rows.length, 1))} of rows below 0.6`} />
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader title="Accounts parsed" subtitle="M1 parser: statement header → account metadata; each row → canonical Transaction with a stable SHA-256 id" />
          <CardBody className="space-y-3">
            {accounts.map((a) => (
              <div key={a.account_id} className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-sm text-sky-200">{a.account_id}</span>
                  <span className="text-ink-400">{a.source_file}</span>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2 text-ink-300 md:grid-cols-3">
                  <span>Bank <b className="text-ink-100">{a.bank ?? "—"}</b></span>
                  <span>Type <b className="text-ink-100">{a.account_type}</b></span>
                  <span>Owner <b className="text-ink-100">{a.legal_owner_type}</b></span>
                  <span>Holder <b className="text-ink-100">{a.holder_name ?? "—"}</b></span>
                  <span>Account <b className="text-ink-100">{a.masked_account ?? "—"}</b></span>
                  <span>Rows <b className="text-ink-100">{a.transactions.toLocaleString("en-IN")}</b></span>
                  <span className="col-span-2">Period <b className="text-ink-100">{a.statement_start} → {a.statement_end}</b></span>
                </div>
              </div>
            ))}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Canonicalisation (Section 3.3)" subtitle="Intraday order is fixed, then the opening balance of every row is derived from the closing one" />
          <CardBody className="space-y-4">
            <Formula>balance_before = balance_after − credit + debit</Formula>
            {example && (
              <div>
                <Note>First transaction of the stream:</Note>
                <div className="mt-2 rounded-xl bg-white/[0.02] px-4 py-2">
                  <CalcLine label="balance_after (from statement)" value={inr(example.balance_after, 2)} />
                  <CalcLine op={example.direction === "CREDIT" ? "−" : "+"} label={`${String(example.direction).toLowerCase()} amount`} value={inr(example.amount, 2)} />
                  <CalcLine op="=" label="balance_before" value={inr(example.balance_before, 2)} emphasis />
                </div>
              </div>
            )}
            <div>
              <Note>Narration normalisation: Unicode NFKC, control characters removed, repeated separators and whitespace collapsed, upper-cased (raw → normalised).</Note>
              <div className="mt-2 space-y-1.5">
                {stats.changed.map((r) => (
                  <div key={String(r.transaction_id)} className="rounded-lg bg-white/[0.02] px-3 py-2 font-mono text-[11px]">
                    <div className="truncate text-ink-400">{String(r.raw_narration)}</div>
                    <div className="truncate text-ink-100">{String(r.normalized_narration)}</div>
                  </div>
                ))}
                {stats.changed.length === 0 && <Note>Every narration was already in canonical form.</Note>}
              </div>
            </div>
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader title="Channel families (Section 3.4)" subtitle="The statement's Mode column gives the payment rail; when Mode is Other, the Payment Mode category decides (Bank Charges → fee, Interest Received → interest). Narration text is not used." />
        <CardBody>
          <Legend items={[{ label: "Credit amount", color: "#34d399" }, { label: "Debit amount", color: "#fb7185" }]} />
          <SeriesChart
            data={stats.channels}
            xKey="channel"
            height={260}
            series={[
              { key: "credit", label: "Credits", color: "#34d399", type: "bar" },
              { key: "debit", label: "Debits", color: "#fb7185", type: "bar" },
            ]}
          />
          <div className="mt-4 grid gap-x-8 text-xs md:grid-cols-3">
            {stats.channels.map((c) => (
              <div key={c.channel} className="flex justify-between border-b border-white/[0.04] py-1.5">
                <span className="font-mono text-ink-200">{c.channel}</span>
                <span className="text-ink-400 tabular">{c.count.toLocaleString("en-IN")} txns</span>
              </div>
            ))}
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Largest transactions" subtitle="Open any one to see how every later step treats it" />
        <CardBody>
          {[...rows]
            .sort((a, b) => (b.amount as number) - (a.amount as number))
            .slice(0, 8)
            .map((r) => <TxnLink key={String(r.transaction_id)} row={r} onOpen={onOpenTxn} />)}
        </CardBody>
      </Card>
    </div>
  );
}
