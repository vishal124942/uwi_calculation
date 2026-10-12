"use client";

import { Download, X } from "lucide-react";
import { useMemo, useState } from "react";
import { inr, inrShort, pct } from "@/lib/format";
import { roleColor, roleLabel } from "@/lib/roles";
import type { TraceState } from "@/lib/trace";
import type { Meta, Row } from "@/lib/types";
import DataTable from "./DataTable";
import { useTxnRows } from "./steps/shared";
import { Card, CardBody, CardHeader, cx, Empty, Stat, Tabs } from "./ui";

type Stage = "final" | "rules" | "model";
type Direction = "CREDIT" | "DEBIT";

const STAGES: Record<Stage, { label: string; role: string; p: string; hint: string }> = {
  final: { label: "Final role (M2 + M3 + M4)", role: "s05_top_role", p: "s05_top_p", hint: "after the rule overlay and flow-pair evidence; this is what the ledger uses" },
  rules: { label: "After rules (M3)", role: "s04_top_role", p: "s04_top_p", hint: "calibrated model probabilities after the deterministic rule overlay" },
  model: { label: "Model only (M2)", role: "s04_calibrated_top_role", p: "s04_calibrated_top_p", hint: "calibrated role-classifier output before any rule" },
};

const ALL = "__all__";

interface RoleStat {
  role: string;
  count: number;
  amount: number;
  confidence: number;
}

interface Distribution {
  rows: Row[];
  count: number;
  amount: number;
  roles: RoleStat[];
}

const amountOf = (r: Row) => (typeof r.amount === "number" ? r.amount : 0);

function distribution(rows: Row[], direction: Direction, codes: string[], roleCol: string, pCol: string): Distribution {
  const list = rows.filter((r) => r.direction === direction);
  const acc = new Map<string, RoleStat>(codes.map((c) => [c, { role: c, count: 0, amount: 0, confidence: 0 }]));
  for (const r of list) {
    const code = String(r[roleCol] ?? "");
    if (!code) continue;
    const s = acc.get(code) ?? { role: code, count: 0, amount: 0, confidence: 0 };
    s.count += 1;
    s.amount += amountOf(r);
    s.confidence += typeof r[pCol] === "number" ? (r[pCol] as number) : 0;
    acc.set(code, s);
  }
  const roles = [...acc.values()].map((s) => ({ ...s, confidence: s.count ? s.confidence / s.count : 0 }));
  return { rows: list, count: list.length, amount: list.reduce((n, r) => n + amountOf(r), 0), roles };
}

function ShareBar({ value, colour }: { value: number; colour: string }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/[0.05]">
      <div className="h-full rounded-full transition-all duration-500" style={{ width: `${Math.min(100, value * 100)}%`, background: colour }} />
    </div>
  );
}

function RoleTable({
  title,
  dist,
  roles,
  selected,
  onSelect,
}: {
  title: string;
  dist: Distribution;
  roles?: Record<string, string>;
  selected: string | null;
  onSelect: (role: string) => void;
}) {
  const used = dist.roles.filter((r) => r.count > 0).length;
  return (
    <Card>
      <CardHeader
        title={title}
        subtitle={`${dist.count.toLocaleString("en-IN")} transactions · ${inr(dist.amount)} · ${used} of ${dist.roles.length} roles used. Click a role to list its transactions.`}
      />
      <div>
        <div className="grid grid-cols-[minmax(12rem,1.3fr)_4.5rem_minmax(7rem,1fr)_7.5rem_minmax(7rem,1fr)_4rem] gap-x-3 border-b border-white/[0.06] px-5 py-2 text-[10px] font-semibold uppercase tracking-wider text-ink-400">
          <span>Role</span>
          <span className="text-right">Count</span>
          <span>% of count</span>
          <span className="text-right">Amount</span>
          <span>% of amount</span>
          <span className="text-right" title="Average top-role probability">Conf.</span>
        </div>
        <div className="divide-y divide-white/[0.03]">
          {dist.roles.map((r) => {
            const countShare = dist.count ? r.count / dist.count : 0;
            const amountShare = dist.amount ? r.amount / dist.amount : 0;
            const colour = roleColor(r.role);
            const active = selected === r.role;
            return (
              <button
                key={r.role}
                disabled={!r.count}
                onClick={() => onSelect(r.role)}
                className={cx(
                  "grid w-full grid-cols-[minmax(12rem,1.3fr)_4.5rem_minmax(7rem,1fr)_7.5rem_minmax(7rem,1fr)_4rem] items-center gap-x-3 px-5 py-2 text-left text-xs transition",
                  r.count ? "hover:bg-white/[0.03]" : "cursor-default opacity-35",
                  active && "bg-sky-400/[0.07] ring-1 ring-inset ring-sky-400/30",
                )}
              >
                <span className="flex min-w-0 items-center gap-2">
                  <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: colour }} />
                  <span className="font-mono font-semibold" style={{ color: colour }}>
                    {r.role}
                  </span>
                  <span className="truncate text-ink-200">{roleLabel(roles, r.role)}</span>
                </span>
                <span className="text-right font-mono text-ink-100 tabular">{r.count.toLocaleString("en-IN")}</span>
                <span className="flex items-center gap-1.5">
                  <ShareBar value={countShare} colour={colour} />
                  <span className="w-10 shrink-0 text-right text-[10.5px] text-ink-300 tabular">{pct(countShare, countShare < 0.1 ? 1 : 0)}</span>
                </span>
                <span className="text-right font-mono text-ink-200 tabular">{inr(r.amount)}</span>
                <span className="flex items-center gap-1.5">
                  <ShareBar value={amountShare} colour={colour} />
                  <span className="w-10 shrink-0 text-right text-[10.5px] text-ink-300 tabular">{pct(amountShare, amountShare < 0.1 ? 1 : 0)}</span>
                </span>
                <span className="text-right text-[11px] text-ink-300 tabular">{r.count ? pct(r.confidence, 0) : "—"}</span>
              </button>
            );
          })}
        </div>
        <div className="grid grid-cols-[minmax(12rem,1.3fr)_4.5rem_minmax(7rem,1fr)_7.5rem_minmax(7rem,1fr)_4rem] gap-x-3 border-t border-white/[0.06] px-5 py-2 text-xs font-semibold">
          <span className="text-ink-300">Total</span>
          <span className="text-right font-mono text-ink-100 tabular">{dist.count.toLocaleString("en-IN")}</span>
          <span className="text-[10.5px] text-ink-400">100%</span>
          <span className="text-right font-mono text-ink-100 tabular">{inr(dist.amount)}</span>
          <span className="text-[10.5px] text-ink-400">100%</span>
          <span />
        </div>
      </div>
    </Card>
  );
}

function downloadCsv(name: string, lines: (string | number)[][]) {
  const text = lines.map((l) => l.map((v) => (typeof v === "string" && /[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v)).join(",")).join("\n");
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

/** Transactions per credit role (C01–C13) and debit role (D01–D19), for each uploaded document. */
export default function RoleDistribution({ trace, meta, onOpenTxn }: { trace: TraceState; meta: Meta | null; onOpenTxn: (id: string) => void }) {
  const rows = useTxnRows(trace);
  const roles = meta?.roles;
  const [doc, setDoc] = useState(ALL);
  const [stage, setStage] = useState<Stage>("final");
  const [selected, setSelected] = useState<{ direction: Direction; role: string } | null>(null);
  const { role: roleCol, p: pCol } = STAGES[stage];

  const codes = useMemo(() => {
    const all = Object.keys(roles ?? {}).sort();
    return { CREDIT: all.filter((c) => c.startsWith("C")), DEBIT: all.filter((c) => c.startsWith("D")) };
  }, [roles]);

  const docs = useMemo(() => {
    const counts = new Map<string, number>();
    for (const r of rows) counts.set(String(r.account_id), (counts.get(String(r.account_id)) ?? 0) + 1);
    const info = new Map((trace.request?.accounts ?? []).map((a) => [a.account_id, a]));
    return [...counts].map(([id, n]) => ({ id, count: n, file: info.get(id)?.source_file ?? null, holder: info.get(id)?.holder_name ?? null }));
  }, [rows, trace.request]);

  const docRows = useMemo(() => (doc === ALL ? rows : rows.filter((r) => String(r.account_id) === doc)), [rows, doc]);
  const credit = useMemo(() => distribution(docRows, "CREDIT", codes.CREDIT, roleCol, pCol), [docRows, codes, roleCol, pCol]);
  const debit = useMemo(() => distribution(docRows, "DEBIT", codes.DEBIT, roleCol, pCol), [docRows, codes, roleCol, pCol]);

  const perDoc = useMemo(
    () =>
      docs.map((d) => {
        const own = rows.filter((r) => String(r.account_id) === d.id);
        return { doc: d.id, CREDIT: distribution(own, "CREDIT", codes.CREDIT, roleCol, pCol), DEBIT: distribution(own, "DEBIT", codes.DEBIT, roleCol, pCol) };
      }),
    [docs, rows, codes, roleCol, pCol],
  );

  const selectedRows = useMemo(() => {
    if (!selected) return [];
    return (selected.direction === "CREDIT" ? credit : debit).rows.filter((r) => r[roleCol] === selected.role);
  }, [selected, credit, debit, roleCol]);

  if (!rows.length || !rows.some((r) => roleCol in r)) return <Empty>Role distribution appears once the role classifier (M2) has run.</Empty>;

  const unknown = (credit.roles.find((r) => r.role === "C13")?.count ?? 0) + (debit.roles.find((r) => r.role === "D19")?.count ?? 0);
  const total = credit.count + debit.count;
  const meanConfidence = total ? [...credit.roles, ...debit.roles].reduce((n, r) => n + r.confidence * r.count, 0) / total : 0;
  const docLabel = doc === ALL ? (docs.length > 1 ? "all documents" : docs[0]?.id ?? "") : doc;
  const select = (direction: Direction, role: string) =>
    setSelected((s) => (s && s.direction === direction && s.role === role ? null : { direction, role }));

  const drill = selected && (
    <Card>
      <CardHeader
        title={
          <span className="flex items-center gap-2">
            <span className="font-mono" style={{ color: roleColor(selected.role) }}>
              {selected.role}
            </span>
            {roleLabel(roles, selected.role)}
            <span className="font-normal text-ink-400">
              · {selectedRows.length.toLocaleString("en-IN")} transactions in {docLabel}
            </span>
          </span>
        }
        subtitle={`${inr(selectedRows.reduce((n, r) => n + amountOf(r), 0))} in total. Click a row to open its role-classifier trace: evidence, model, calibration, rules and pairing.`}
        right={
          <button onClick={() => setSelected(null)} className="rounded-lg p-1.5 text-ink-400 hover:bg-white/5 hover:text-ink-100" aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        }
      />
      <CardBody>
        <DataTable
          key={`${doc}-${stage}-${selected.direction}-${selected.role}`}
          columns={[
            "booking_date",
            ...(doc === ALL && docs.length > 1 ? ["account_id"] : []),
            "amount",
            "normalized_narration",
            "s03_channel_family",
            roleCol,
            pCol,
            "s04_second_role",
            "s04_second_p",
            "s04_rules_applied",
            ...(stage === "final" ? ["s05_role_changed", "s05_pair_type"] : []),
            "transaction_id",
          ].filter((c) => c in (selectedRows[0] ?? {}))}
          rows={selectedRows}
          height={460}
          onRowClick={(r) => onOpenTxn(String(r.transaction_id))}
          downloadName={`${docLabel.replace(/\s+/g, "_")}_${selected.role}_transactions`}
          title={`${selected.role} · ${roleLabel(roles, selected.role)}`}
        />
      </CardBody>
    </Card>
  );

  const exportCounts = () => {
    const lines: (string | number)[][] = [["doc_id", "stage", "direction", "role", "role_name", "count", "count_share", "amount", "amount_share", "avg_top_role_probability"]];
    for (const d of perDoc)
      for (const dir of ["CREDIT", "DEBIT"] as Direction[]) {
        const dist = d[dir];
        for (const r of dist.roles)
          lines.push([d.doc, roleCol, dir, r.role, roleLabel(roles, r.role), r.count, dist.count ? +(r.count / dist.count).toFixed(6) : 0, +r.amount.toFixed(2), dist.amount ? +(r.amount / dist.amount).toFixed(6) : 0, r.count ? +r.confidence.toFixed(4) : ""]);
      }
    downloadCsv(`role_distribution_${stage}.csv`, lines);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-sky-300/80">Role classifier</div>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">Role distribution by document</h1>
          <p className="mt-1 max-w-3xl text-sm text-ink-300">
            How many transactions of each uploaded document fall into each credit role (C01–C13) and debit role (D01–D19), with their share of count and
            amount. Click a role to see exactly which transactions are in it, then click a transaction for its full role-classifier trace.
          </p>
        </div>
        <button
          onClick={exportCounts}
          className="inline-flex items-center gap-1.5 rounded-lg border border-white/[0.08] px-3 py-1.5 text-xs text-ink-200 transition hover:border-sky-400/40 hover:text-sky-200"
        >
          <Download className="h-3.5 w-3.5" /> Counts per document (CSV)
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Tabs
          value={doc}
          onChange={(v) => {
            setDoc(v);
            setSelected(null);
          }}
          tabs={[
            ...(docs.length > 1 ? [{ id: ALL, label: "All documents", count: rows.length }] : []),
            ...docs.map((d) => ({ id: d.id, label: <span title={[d.file, d.holder].filter(Boolean).join(" · ")}>{d.id}</span>, count: d.count })),
          ]}
        />
        <Tabs
          value={stage}
          onChange={(v) => {
            setStage(v);
            setSelected(null);
          }}
          tabs={(Object.keys(STAGES) as Stage[]).map((s) => ({ id: s, label: STAGES[s].label }))}
        />
      </div>
      <p className="-mt-3 text-xs text-ink-400">
        Showing <span className="text-ink-200">{docLabel}</span> · {STAGES[stage].label}: {STAGES[stage].hint}.
      </p>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Stat label="Transactions" value={total.toLocaleString("en-IN")} />
        <Stat label="Credits" value={credit.count.toLocaleString("en-IN")} hint={inrShort(credit.amount)} tone="income" />
        <Stat label="Debits" value={debit.count.toLocaleString("en-IN")} hint={inrShort(debit.amount)} tone="deduct" />
        <Stat label="Unknown (C13 / D19)" value={unknown.toLocaleString("en-IN")} hint={`${pct(total ? unknown / total : 0)} of transactions`} />
        <Stat label="Avg top-role probability" value={pct(meanConfidence)} />
      </div>

      <RoleTable title="Credit roles" dist={credit} roles={roles} selected={selected?.direction === "CREDIT" ? selected.role : null} onSelect={(r) => select("CREDIT", r)} />
      {selected?.direction === "CREDIT" && drill}
      <RoleTable title="Debit roles" dist={debit} roles={roles} selected={selected?.direction === "DEBIT" ? selected.role : null} onSelect={(r) => select("DEBIT", r)} />
      {selected?.direction === "DEBIT" && drill}

      {docs.length > 1 && (
        <Card>
          <CardHeader title="Compare documents" subtitle="Transaction count per role in each uploaded document (share of that document's credits or debits). Click a cell to drill in." />
          <CardBody className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wider text-ink-400">
                  <th className="py-1.5 pr-3 font-semibold">Role</th>
                  {perDoc.map((d) => (
                    <th key={d.doc} className="px-3 py-1.5 text-right font-mono font-semibold normal-case">
                      {d.doc}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(["CREDIT", "DEBIT"] as Direction[]).flatMap((dir) =>
                  codes[dir]
                    .filter((code) => perDoc.some((d) => d[dir].roles.find((r) => r.role === code)?.count))
                    .map((code) => (
                      <tr key={code} className="border-t border-white/[0.04]">
                        <td className="py-1.5 pr-3">
                          <span className="font-mono font-semibold" style={{ color: roleColor(code) }}>
                            {code}
                          </span>{" "}
                          <span className="text-ink-300">{roleLabel(roles, code)}</span>
                        </td>
                        {perDoc.map((d) => {
                          const s = d[dir].roles.find((r) => r.role === code);
                          const n = s?.count ?? 0;
                          return (
                            <td key={d.doc} className="px-3 py-1.5 text-right tabular">
                              {n ? (
                                <button
                                  className="rounded px-1 hover:bg-white/5 hover:text-sky-200"
                                  onClick={() => {
                                    setDoc(d.doc);
                                    setSelected({ direction: dir, role: code });
                                  }}
                                >
                                  <span className="font-mono text-ink-100">{n.toLocaleString("en-IN")}</span>
                                  <span className="ml-1.5 text-ink-400">{pct(d[dir].count ? n / d[dir].count : 0, 0)}</span>
                                </button>
                              ) : (
                                <span className="text-ink-500">—</span>
                              )}
                            </td>
                          );
                        })}
                      </tr>
                    )),
                )}
              </tbody>
            </table>
          </CardBody>
        </Card>
      )}
    </div>
  );
}
