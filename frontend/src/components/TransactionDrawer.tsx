"use client";

import { X } from "lucide-react";
import { type ReactNode, useEffect } from "react";
import { cellText, fixed, inr, pct } from "@/lib/format";
import { roleColor, roleLabel } from "@/lib/roles";
import type { TraceState } from "@/lib/trace";
import type { Cell, Meta, Row } from "@/lib/types";
import { Badge, CalcLine, cx, KeyValueGrid, ProbBars } from "./ui";

function pick(row: Row, prefix: string, skip: RegExp = /^$/): Record<string, Cell> {
  return Object.fromEntries(
    Object.entries(row)
      .filter(([k, v]) => k.startsWith(prefix) && !skip.test(k) && v !== null && v !== "" && !(Array.isArray(v) && v.length === 0))
      .map(([k, v]) => [k.slice(prefix.length), v]),
  );
}

function Stage({ code, title, children, done = true }: { code: string; title: string; children: ReactNode; done?: boolean }) {
  const model = /^M\d$/.test(code);
  return (
    <div className="relative pl-12">
      <span
        className={cx(
          "absolute left-0 top-0 flex h-6 w-10 items-center justify-center rounded-md font-mono text-[10px] font-semibold ring-1",
          model ? "bg-sky-400/15 text-sky-200 ring-sky-400/30" : "bg-white/[0.05] text-ink-300 ring-white/10",
        )}
      >
        {code}
      </span>
      <span className="absolute bottom-0 left-5 top-7 w-px bg-white/[0.06]" />
      <div className="pb-6">
        <div className="mb-2 text-sm font-semibold text-ink-100">{title}</div>
        {done ? children : <div className="text-xs text-ink-400">Not reached yet.</div>}
      </div>
    </div>
  );
}

function RoleLine({ roles, role, p }: { roles?: Record<string, string>; role: Cell | undefined; p: Cell | undefined }) {
  return (
    <div className="text-xs text-ink-300">
      Top role <span className="font-mono" style={{ color: roleColor(String(role)) }}>{String(role)}</span> {roleLabel(roles, String(role))} at {pct(p)}
    </div>
  );
}

export default function TransactionDrawer({ id, trace, meta, onClose }: { id: string; trace: TraceState; meta: Meta | null; onClose: () => void }) {
  const row = trace.txns.get(id);
  const rt = trace.roleTrace?.[id];
  const roles = meta?.roles;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!row) return null;
  const credit = row.direction === "CREDIT";
  const buckets = Object.fromEntries(
    Object.entries(pick(row, "s06_", /p_operating|role_uncertainty|cash_business_probability/)).filter(([, v]) => typeof v === "number" && v > 0.005),
  );

  return (
    <div data-txn-drawer className="fixed inset-0 z-40 flex justify-end">
      <button aria-label="Close" onClick={onClose} className="absolute inset-0 bg-ink-950/60 backdrop-blur-[2px]" />
      <aside className="rise relative flex h-full w-full max-w-2xl flex-col border-l border-white/10 bg-ink-900 shadow-2xl">
        <div className="flex items-start gap-4 border-b border-white/[0.07] px-6 py-5">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 text-xs text-ink-400">
              <Badge tone={credit ? "good" : "bad"}>{String(row.direction)}</Badge>
              <span className="tabular">{String(row.booking_date)}</span>
              <span className="font-mono">{id}</span>
            </div>
            <div className={`mt-2 font-mono text-3xl font-semibold tabular ${credit ? "text-emerald-300" : "text-rose-300"}`}>
              {credit ? "+" : "−"}
              {inr(row.amount, 2)}
            </div>
            <div className="mt-1 break-all font-mono text-xs text-ink-300">{String(row.raw_narration ?? "—")}</div>
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-ink-400 hover:bg-white/5 hover:text-ink-100" aria-label="Close">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-6">
          <Stage code="M1" title="Parser/normaliser: canonical transaction">
            <div className="rounded-xl bg-white/[0.02] px-4 py-2">
              <CalcLine label="balance before" value={inr(row.balance_before, 2)} />
              <CalcLine op={credit ? "+" : "−"} label="amount" value={inr(row.amount, 2)} />
              <CalcLine op="=" label="balance after" value={inr(row.balance_after, 2)} emphasis />
            </div>
            <div className="mt-2 text-xs text-ink-300">
              Normalised: <span className="font-mono text-ink-100">{String(row.normalized_narration ?? "—")}</span> · channel{" "}
              <Badge>{String(row.s01_channel_family)}</Badge> from Mode{" "}
              <span className="font-mono text-ink-100">{String(row.s01_mode ?? "—")}</span> / Payment Mode{" "}
              <span className="font-mono text-ink-100">{String(row.s01_payment_mode ?? "—")}</span> · account{" "}
              {String(row.account_id)}
            </div>
          </Stage>

          <Stage code="GATE" title="Statement integrity gate" done={"s02_reconciliation_break" in row}>
            <div className="text-xs text-ink-300">
              Reconciliation error {row.s02_reconciliation_error == null ? "— (first row or no balance)" : inr(row.s02_reconciliation_error, 2)} ·{" "}
              {row.s02_reconciliation_break ? <Badge tone="bad">balance break</Badge> : <Badge tone="good">reconciles</Badge>}
            </div>
          </Stage>

          <Stage code="M2" title="Role classifier: feature inputs and calibrated probabilities" done={"s03_entity_cluster_id" in row}>
            <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
              <Badge tone="info">{String(row.s03_entity_status)}</Badge>
              <span className="text-ink-100">{String(row.s03_entity_label ?? "unlabelled counterparty")}</span>
              <span className="text-ink-400">
                match p {fixed(row.s03_entity_match_probability, 2)} · {cellText(row.s03_entity_txn_count)} txns over {cellText(row.s03_entity_active_months)} months
              </span>
            </div>
            <KeyValueGrid columns={1} data={pick(row, "s03_id_")} />
            <details className="mt-2">
              <summary className="cursor-pointer text-xs text-sky-300">Neighbourhood features</summary>
              <div className="mt-2">
                <KeyValueGrid columns={1} data={pick(row, "s03_NF")} />
              </div>
            </details>
            {"s04_calibrated_top_role" in row && (
              <div className="mt-4 space-y-4">
                {rt ? (
                  (
                    [
                      ["Model (softmax of scores)", rt.model],
                      ["Calibrated", rt.calibrated],
                    ] as const
                  ).map(([t, p]) => (
                    <div key={t}>
                      <div className="mb-1.5 text-[10px] uppercase tracking-wider text-ink-400">{t}</div>
                      <ProbBars probs={p} labels={roles} colorOf={roleColor} limit={4} />
                    </div>
                  ))
                ) : (
                  <RoleLine roles={roles} role={row.s04_calibrated_top_role} p={row.s04_calibrated_top_p} />
                )}
              </div>
            )}
          </Stage>

          <Stage code="M3" title="Rule overlay" done={"s04_top_role" in row}>
            {rt ? (
              <div className="space-y-3">
                {rt.rules.length === 0 && <div className="text-xs text-ink-400">No rule fired; the calibrated distribution passes through unchanged.</div>}
                {rt.rules.map((a) => (
                  <div key={a.rule_id} className="text-xs text-ink-300">
                    <Badge tone="info">{a.rule_id}</Badge> <span className="ml-1">{a.action} · {a.description}</span>
                  </div>
                ))}
                {rt.rules.length > 0 && (
                  <div>
                    <div className="mb-1.5 text-[10px] uppercase tracking-wider text-ink-400">After rules</div>
                    <ProbBars probs={rt.after_rules} labels={roles} colorOf={roleColor} limit={4} />
                  </div>
                )}
              </div>
            ) : (
              <RoleLine roles={roles} role={row.s04_top_role} p={row.s04_top_p} />
            )}
          </Stage>

          <Stage code="M4" title="Flow-pair model and multi-account" done={"s05_top_role" in row}>
            <div className="space-y-3 text-xs text-ink-300">
              {row.s05_pair_type ? (
                <div>
                  Paired as <Badge tone="policy">{String(row.s05_pair_type)}</Badge> with{" "}
                  <span className="font-mono text-ink-100">{String(row.s05_pair_partner_txn)}</span> (score {fixed(row.s05_pair_score, 3)})
                </div>
              ) : (
                <div>Not part of any flow pair.</div>
              )}
              {rt?.pair_adjustments?.map((a) => (
                <div key={a.rule_id}>
                  <Badge tone="policy">{a.rule_id}</Badge> <span className="ml-1">{a.description}</span>
                </div>
              ))}
              {rt?.final && (
                <div>
                  <div className="mb-1.5 text-[10px] uppercase tracking-wider text-ink-400">Final distribution · entropy {fixed(rt.entropy, 3)}</div>
                  <ProbBars probs={rt.final} labels={roles} colorOf={roleColor} limit={4} />
                </div>
              )}
            </div>
          </Stage>

          <Stage code="LEDGER" title="Economic ledger" done={"s06_p_operating" in row}>
            {credit ? (
              <div className="rounded-xl bg-white/[0.02] px-4 py-2">
                <CalcLine label="amount" value={inr(row.amount, 2)} />
                <CalcLine op="×" label="P_operating = P(C01)+P(C02)+cash_eligibility·P(C03)" value={fixed(row.s06_p_operating, 4)} />
                <CalcLine op="=" label="contribution to EOC" value={inr(row.s06_eoc_credit ?? 0, 2)} emphasis />
              </div>
            ) : (
              <div className="rounded-xl bg-white/[0.02] px-4 py-2">
                <CalcLine label="amount" value={inr(row.amount, 2)} />
                <CalcLine op="×" label="P(core operating roles)" value={fixed(((row.s06_cor_debit as number) ?? 0) / (row.amount as number), 4)} />
                <CalcLine op="=" label="contribution to COR" value={inr(row.s06_cor_debit ?? 0, 2)} emphasis />
              </div>
            )}
            <div className="mt-3 text-[11px] text-ink-400">Every bucket this transaction feeds (probability-weighted rupees):</div>
            <div className="mt-1">
              <KeyValueGrid columns={1} data={buckets} format={(_k, v) => inr(v, 2)} />
            </div>
          </Stage>

          <div className="pl-12 text-xs text-ink-400">
            M5 archetype, M6 cycle, the risk signals, M7 income, M8 uncertainty and M9 policy work on these ledger totals, not on single transactions.
          </div>
        </div>
      </aside>
    </div>
  );
}
