"use client";

import { useMemo, useState } from "react";
import { componentColumns } from "@/lib/components";
import { roleLabel } from "@/lib/roles";
import type { TraceState } from "@/lib/trace";
import type { Meta } from "@/lib/types";
import DataTable from "./DataTable";
import { useTxnRows } from "./steps/shared";
import { Card, cx, Empty } from "./ui";

const KEY_COLUMNS = [
  "transaction_id", "booking_date", "direction", "amount", "normalized_narration", "s03_channel_family",
  "s03_entity_label", "s05_top_role", "s05_top_p", "s06_p_operating", "s06_eoc_credit", "s06_cor_debit",
];

export default function TransactionExplorer({
  trace,
  meta,
  selected,
  onOpenTxn,
}: {
  trace: TraceState;
  meta: Meta | null;
  selected: string | null;
  onOpenTxn: (id: string) => void;
}) {
  const rows = useTxnRows(trace);
  const [groups, setGroups] = useState<Set<string>>(new Set());
  const [direction, setDirection] = useState<"ALL" | "CREDIT" | "DEBIT">("ALL");
  const [role, setRole] = useState("");

  const owners = useMemo(
    () => (meta?.components ?? []).map((c) => ({ c, columns: componentColumns(c, trace) })).filter((o) => o.columns.length > 0),
    [meta, trace],
  );
  const extra = useMemo(() => owners.filter((o) => groups.has(o.c.id)).flatMap((o) => o.columns), [owners, groups]);
  const columns = useMemo(() => {
    const available = new Set(Object.keys(rows[0] ?? {}));
    return [...new Set([...KEY_COLUMNS, ...extra])].filter((c) => available.has(c));
  }, [extra, rows]);
  const highlight = useMemo(() => new Set(extra), [extra]);

  const roleOptions = useMemo(() => [...new Set(rows.map((r) => String(r.s05_top_role ?? r.s04_top_role ?? "")).filter(Boolean))].sort(), [rows]);
  const filtered = useMemo(
    () =>
      rows.filter(
        (r) => (direction === "ALL" || r.direction === direction) && (!role || (r.s05_top_role ?? r.s04_top_role) === role),
      ),
    [rows, direction, role],
  );

  if (!rows.length) return <Empty>Run an analysis first.</Empty>;

  return (
    <div className="rise space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Transaction journey</h1>
        <p className="mt-1 text-sm text-ink-300">
          Every transaction with the columns each component added. Add a component&apos;s columns below, filter, sort or search, then click a row to follow
          it through M1 parsing, the integrity gate, M2 evidence and role model, M3 rules, M4 pairing and the economic ledger.
        </p>
      </div>
      <Card>
        <div className="space-y-4 p-5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="mr-1 text-[11px] font-semibold uppercase tracking-wider text-ink-400">Add columns from</span>
            {owners.map(({ c, columns: cols }) => (
              <button
                key={c.id}
                title={c.name}
                onClick={() =>
                  setGroups((g) => {
                    const next = new Set(g);
                    if (next.has(c.id)) next.delete(c.id);
                    else next.add(c.id);
                    return next;
                  })
                }
                className={cx(
                  "inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs transition",
                  groups.has(c.id) ? "border-sky-400/40 bg-sky-400/10 text-sky-200" : "border-white/[0.08] text-ink-300 hover:text-ink-100",
                )}
              >
                {c.kind === "model" && <span className="font-mono font-semibold">{c.id}</span>}
                {c.name} · {cols.length}
              </button>
            ))}
          </div>
          <DataTable
            columns={columns}
            rows={filtered}
            highlight={highlight}
            height={640}
            selectedKey={selected}
            onRowClick={(r) => onOpenTxn(String(r.transaction_id))}
            downloadName="transactions"
            title="Transaction journey"
            toolbar={
              <>
                <select
                  value={direction}
                  onChange={(e) => setDirection(e.target.value as typeof direction)}
                  className="rounded-lg border border-white/[0.08] bg-ink-850 px-2.5 py-1.5 text-xs"
                >
                  <option value="ALL">All directions</option>
                  <option value="CREDIT">Credits</option>
                  <option value="DEBIT">Debits</option>
                </select>
                <select value={role} onChange={(e) => setRole(e.target.value)} className="max-w-56 rounded-lg border border-white/[0.08] bg-ink-850 px-2.5 py-1.5 text-xs">
                  <option value="">All top roles</option>
                  {roleOptions.map((r) => (
                    <option key={r} value={r}>
                      {r} · {roleLabel(meta?.roles, r)}
                    </option>
                  ))}
                </select>
              </>
            }
          />
        </div>
      </Card>
    </div>
  );
}
