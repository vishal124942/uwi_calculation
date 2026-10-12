"use client";

import { useMemo, useState } from "react";
import { fixed, inr } from "@/lib/format";
import { roleColor, roleLabel } from "@/lib/roles";
import { rowsOf } from "@/lib/trace";
import type { Row } from "@/lib/types";
import { Badge, CalcLine, Card, CardBody, CardHeader, cx, Empty, Formula, Note, ProbBars, Stat } from "../ui";
import { TxnLink, useTxnRows, type StepProps } from "./shared";

const MAX_PAIR_WEIGHT = 0.95;
const FULL_WEIGHT_PAIR_SCORE = 0.7;

export default function Step05({ data, trace, meta, onOpenTxn }: StepProps) {
  const edges = useMemo(() => rowsOf(data.tables.step05_pair_edges), [data]);
  const rows = useTxnRows(trace);
  const byId = useMemo(() => new Map(rows.map((r) => [String(r.transaction_id), r])), [rows]);
  const changed = useMemo(() => rows.filter((r) => r.s05_role_changed === true), [rows]);
  const [selected, setSelected] = useState(0);
  const counts = useMemo(() => {
    const out: Record<string, number> = {};
    for (const e of edges) out[String(e.edge_type)] = (out[String(e.edge_type)] ?? 0) + 1;
    return out;
  }, [edges]);
  const edge: Row | undefined = edges[selected];
  const accounts = trace.request?.accounts.length ?? 1;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="Pairs matched" value={edges.length} />
        <Stat label="Pass-through" value={counts.PASS_THROUGH ?? 0} />
        <Stat label="Recycling" value={counts.RECYCLING ?? 0} />
        <Stat label="Reversal" value={counts.REVERSAL ?? 0} />
        <Stat label="Internal transfer" value={counts.INTERNAL_TRANSFER ?? 0} hint={accounts > 1 ? `${accounts} accounts consolidated` : "single account"} />
      </div>

      <Card>
        <CardHeader title="Flow pairing (Section 8.2) and multi-account matching (Section 17)" subtitle="A credit and a later debit of nearly the same amount can be one movement of money, not income plus cost" />
        <CardBody className="space-y-3">
          <Formula>
            pair_score = amount_similarity × time_decay(Δt) × relationship_prior × direction_compatibility × distinctiveness
            <br />
            distinctiveness = 1 ÷ (number of similar-amount candidates in 24h) &nbsp;·&nbsp; candidates below min_pair_score are dropped, then greedy one-to-one matching
            <br />
            w = {MAX_PAIR_WEIGHT} × min(1, pair_score ÷ {FULL_WEIGHT_PAIR_SCORE}) &nbsp;·&nbsp; P′ = (1 − w)·P + w·onehot(paired role)
          </Formula>
          <Note>
            Pass-through moves both legs towards C12 / D17, recycling towards C04 / D14 (own-money loops), and an exact reversal neutralises both legs
            to C08 / D15. With several accounts, transfers between them are matched here and removed from the economics.
          </Note>
        </CardBody>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[1.1fr_1fr]">
        <Card>
          <CardHeader title={`Matched pairs (${edges.length})`} subtitle="Pick a pair to see the score and the role update" />
          <CardBody className="space-y-1.5">
            {edges.length === 0 && <Empty>No credit/debit pairs passed the score threshold.</Empty>}
            {edges.map((e, i) => (
              <button
                key={String(e.edge_id)}
                onClick={() => setSelected(i)}
                className={cx(
                  "grid w-full grid-cols-[6.5rem_1fr_auto] items-center gap-3 rounded-lg px-3 py-2 text-left text-xs transition",
                  i === selected ? "bg-sky-400/10 ring-1 ring-sky-400/30" : "hover:bg-white/[0.04]",
                )}
              >
                <Badge tone={e.edge_type === "REVERSAL" ? "warn" : e.edge_type === "PASS_THROUGH" ? "policy" : "info"}>{String(e.edge_type)}</Badge>
                <span className="truncate text-ink-300">
                  <span className="text-emerald-300">+{inr(e.credit_amount)}</span> {String(e.credit_date)} →{" "}
                  <span className="text-rose-300">−{inr(e.debit_amount)}</span> {String(e.debit_date)}
                </span>
                <span className="font-mono text-ink-100 tabular">{fixed(e.score, 3)}</span>
              </button>
            ))}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Pair calculation" subtitle={edge ? String(edge.edge_id) : undefined} />
          <CardBody className="space-y-4">
            {!edge ? (
              <Empty>No pair selected.</Empty>
            ) : (
              <>
                <div className="rounded-xl bg-white/[0.02] px-4 py-2">
                  <CalcLine label="amount similarity" value={fixed(edge.amount_similarity, 4)} />
                  <CalcLine op="×" label={`time decay (Δt = ${fixed(edge.dt_hours, 1)} h)`} value={
                    edge.evidence_relationship_prior != null && edge.evidence_distinctiveness != null
                      ? fixed((edge.score as number) / ((edge.amount_similarity as number) * (edge.evidence_relationship_prior as number) * (edge.evidence_distinctiveness as number)), 4)
                      : "—"
                  } />
                  {edge.evidence_relationship_prior != null && <CalcLine op="×" label="relationship prior" value={fixed(edge.evidence_relationship_prior, 4)} />}
                  {edge.evidence_distinctiveness != null && <CalcLine op="×" label="distinctiveness" value={fixed(edge.evidence_distinctiveness, 4)} />}
                  <CalcLine op="=" label="pair score" value={fixed(edge.score, 4)} emphasis />
                  {edge.edge_type !== "REVERSAL" && (
                    <CalcLine
                      op="→"
                      label={`mixture weight w = ${MAX_PAIR_WEIGHT} × min(1, score ÷ ${FULL_WEIGHT_PAIR_SCORE})`}
                      value={fixed(MAX_PAIR_WEIGHT * Math.min(1, (edge.score as number) / FULL_WEIGHT_PAIR_SCORE), 4)}
                    />
                  )}
                </div>
                {(["credit", "debit"] as const).map((leg) => {
                  const id = String(edge[`${leg}_txn_id`]);
                  const row = byId.get(id);
                  const rt = trace.roleTrace?.[id];
                  return (
                    <div key={leg} className="space-y-2">
                      {row && <TxnLink row={row} onOpen={onOpenTxn} />}
                      {rt?.final && (
                        <div className="grid gap-4 md:grid-cols-2">
                          <div>
                            <div className="mb-1 text-[10px] uppercase tracking-wider text-ink-400">before pairing</div>
                            <ProbBars probs={rt.after_rules} labels={meta?.roles} colorOf={roleColor} limit={3} />
                          </div>
                          <div>
                            <div className="mb-1 text-[10px] uppercase tracking-wider text-ink-400">after pairing</div>
                            <ProbBars probs={rt.final} labels={meta?.roles} colorOf={roleColor} limit={3} />
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </>
            )}
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader title={`Transactions whose top role changed through pairing (${changed.length})`} subtitle="Top role after the M3 overlay → top role after pair evidence and inter-account matching" />
        <CardBody>
          {changed.length === 0 && <Empty>Pair evidence shifted probabilities but changed no top role.</Empty>}
          {changed.slice(0, 40).map((r) => (
            <TxnLink key={String(r.transaction_id)} row={r} onOpen={onOpenTxn}>
              <span className="font-mono" style={{ color: roleColor(String(r.s04_top_role)) }}>{String(r.s04_top_role)}</span>
              {" → "}
              <span className="font-mono" style={{ color: roleColor(String(r.s05_top_role)) }}>{String(r.s05_top_role)}</span>{" "}
              <span className="text-ink-400">{roleLabel(meta?.roles, String(r.s05_top_role))}</span> · {String(r.normalized_narration ?? "")}
            </TxnLink>
          ))}
        </CardBody>
      </Card>
    </div>
  );
}
