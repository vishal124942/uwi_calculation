"use client";

import { useMemo, useState } from "react";
import { cellText, inr, inrShort, pct } from "@/lib/format";
import { rowsOf } from "@/lib/trace";
import type { Cell, Row } from "@/lib/types";
import { BarList } from "../charts";
import { Badge, Card, CardBody, CardHeader, Formula, KeyValueGrid, Note, type Tone } from "../ui";
import { groupBy, sum, TxnLink, useTxnRows, type StepProps } from "./shared";

const ID_FIELDS: { col: string; label: string }[] = [
  { col: "s03_id_vpa_local", label: "UPI VPA (handle)" },
  { col: "s03_id_vpa_psp", label: "UPI PSP" },
  { col: "s03_id_bank_code", label: "Counterparty bank code" },
  { col: "s03_id_ifsc", label: "IFSC" },
  { col: "s03_id_utr", label: "UTR / RRN" },
  { col: "s03_id_name_tokens", label: "Name tokens" },
  { col: "s03_id_account_fragment", label: "Account fragment" },
  { col: "s03_id_mandate_id", label: "NACH mandate" },
  { col: "s03_id_cheque_no", label: "Cheque number" },
  { col: "s03_id_merchant_id", label: "Merchant id" },
  { col: "s03_id_own_account_marker", label: "Own-account marker" },
  { col: "s03_id_holder_name_match", label: "Holder-name match > 0" },
];

const STATUS_TONE: Record<string, Tone> = { DETERMINISTIC: "good", PROBABLE: "info", BEHAVIOURAL_ONLY: "warn", UNRESOLVED: "neutral" };
const STATUS_COLOR: Record<string, string> = { DETERMINISTIC: "#34d399", PROBABLE: "#38bdf8", BEHAVIOURAL_ONLY: "#fbbf24", UNRESOLVED: "#66748b" };

function present(v: Cell | undefined): boolean {
  if (v === null || v === undefined || v === "" || v === false) return false;
  if (Array.isArray(v)) return v.length > 0;
  if (typeof v === "number") return v > 0;
  return true;
}

export default function Step03({ data, trace, onOpenTxn }: StepProps) {
  const rows = useTxnRows(trace);
  const entities = useMemo(() => rowsOf(data.tables.step03_entities), [data]);
  const [example, setExample] = useState<Row | null>(null);

  const coverage = useMemo(
    () => ID_FIELDS.map((f) => ({ ...f, share: rows.filter((r) => present(r[f.col])).length / Math.max(rows.length, 1) })),
    [rows],
  );
  const statuses = useMemo(
    () =>
      [...groupBy(rows, (r) => String(r.s03_entity_status))]
        .map(([status, list]) => ({ status, count: list.length, amount: sum(list, "amount") }))
        .sort((a, b) => b.amount - a.amount),
    [rows],
  );
  const nf = useMemo(() => {
    const credits = rows.filter((r) => r.direction === "CREDIT");
    const keys = Object.keys(rows[0] ?? {}).filter((k) => /^s03_NF\d{2}_/.test(k));
    const out: Record<string, Cell> = {};
    for (const k of keys) {
      const vals = credits.map((r) => r[k]).filter((v): v is number => typeof v === "number");
      out[k.replace(/^s03_/, "")] = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
    }
    return out;
  }, [rows]);

  const sample = example ?? rows.find((r) => r.direction === "CREDIT" && present(r.s03_id_vpa_local)) ?? rows[0];
  const totalAmount = sum(rows, "amount");

  return (
    <div className="space-y-6">
      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader title="Identifier extraction (Section 5.2)" subtitle="Share of transactions where each identifier was found in the narration" />
          <CardBody>
            <BarList
              format={(v) => pct(v)}
              max={1}
              items={coverage.map((c) => ({ key: c.col.replace("s03_id_", ""), label: c.label, value: c.share, color: "#38bdf8" }))}
            />
            <Note>
              Bank format codes such as TRTR, CRTR or IMPSI are rejected as bank codes and names, so they cannot fake a shared
              counterparty identity.
            </Note>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Entity resolution (Section 5.4)" subtitle={`${entities.length.toLocaleString("en-IN")} latent counterparties; aliases of the same payer/payee collapse into one cluster`} />
          <CardBody className="space-y-4">
            <Formula>
              union-find: transactions sharing any key join one cluster; status = strongest key
              <br />
              DETERMINISTIC · VPA 0.97 · account fragment + IFSC 0.95 · NACH mandate 0.98 · merchant id 0.97
              <br />
              PROBABLE · name + bank code 0.70 · name (≥ 2 tokens) 0.50 · UNRESOLVED · no key
            </Formula>
            <div className="space-y-2">
              {statuses.map((s) => (
                <div key={s.status}>
                  <div className="mb-1 flex justify-between text-xs">
                    <Badge tone={STATUS_TONE[s.status] ?? "neutral"}>{s.status}</Badge>
                    <span className="text-ink-300 tabular">
                      {s.count.toLocaleString("en-IN")} txns · {inrShort(s.amount)} · {pct(s.amount / totalAmount)}
                    </span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.05]">
                    <div className="h-full rounded-full" style={{ width: `${(s.amount / totalAmount) * 100}%`, background: STATUS_COLOR[s.status] }} />
                  </div>
                </div>
              ))}
            </div>
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader title="Most active counterparties" subtitle="Repeat, multi-month counterparties are strong evidence for operating roles in the classifier" />
        <CardBody className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-left text-ink-400">
              <tr className="border-b border-white/[0.06]">
                <th className="py-2 pr-3 font-medium">Entity</th>
                <th className="py-2 pr-3 font-medium">Status</th>
                <th className="py-2 pr-3 text-right font-medium">Txns</th>
                <th className="py-2 pr-3 text-right font-medium">Credits</th>
                <th className="py-2 pr-3 text-right font-medium">Debits</th>
                <th className="py-2 pr-3 text-right font-medium">Active months</th>
                <th className="py-2 font-medium">First seen</th>
              </tr>
            </thead>
            <tbody>
              {entities.slice(0, 15).map((e) => (
                <tr key={String(e.cluster_id)} className="border-b border-white/[0.03]">
                  <td className="max-w-[22rem] truncate py-2 pr-3 text-ink-100">
                    {String(e.canonical_label ?? "—")} <span className="ml-1 font-mono text-[10px] text-ink-500">{String(e.cluster_id)}</span>
                  </td>
                  <td className="py-2 pr-3"><Badge tone={STATUS_TONE[String(e.identity_status)] ?? "neutral"}>{String(e.identity_status)}</Badge></td>
                  <td className="py-2 pr-3 text-right font-mono tabular">{cellText(e.txn_count)}</td>
                  <td className="py-2 pr-3 text-right font-mono text-emerald-300 tabular">{inr(e.credit_amount)}</td>
                  <td className="py-2 pr-3 text-right font-mono text-rose-300 tabular">{inr(e.debit_amount)}</td>
                  <td className="py-2 pr-3 text-right font-mono tabular">{Array.isArray(e.active_months) ? e.active_months.length : "—"}</td>
                  <td className="py-2 text-ink-300">{String(e.first_seen ?? "")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardBody>
      </Card>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader
            title="Neighbourhood features (Section 8.1), average over credits"
            subtitle="What happens around each credit: how fast it leaves, whether a matching amount goes out, how much balance is retained"
          />
          <CardBody>
            <KeyValueGrid data={nf} columns={1} />
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Evidence for one transaction" subtitle="Every feature input the classifier sees for a single row" />
          <CardBody className="space-y-3">
            {sample && (
              <>
                <TxnLink row={sample} onOpen={onOpenTxn} />
                <KeyValueGrid
                  columns={1}
                  data={Object.fromEntries(
                    Object.entries(sample)
                      .filter(([k, v]) => k.startsWith("s03_") && !/^s03_NF/.test(k) && present(v))
                      .map(([k, v]) => [k.replace(/^s03_/, ""), v]),
                  )}
                />
                <button
                  onClick={() => setExample(rows[Math.floor(Math.random() * rows.length)])}
                  className="rounded-lg border border-white/10 px-3 py-1.5 text-xs text-ink-200 hover:bg-white/5"
                >
                  Show another random transaction
                </button>
              </>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
