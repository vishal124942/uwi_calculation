"use client";

import { useMemo, useState } from "react";
import { inr, inrShort, pct } from "@/lib/format";
import { roleColor, roleLabel } from "@/lib/roles";
import type { Row } from "@/lib/types";
import { BarList } from "../charts";
import { Badge, Card, CardBody, CardHeader, cx, Empty, Formula, Note, ProbBars } from "../ui";
import { groupBy, sum, TxnLink, useTxnRows, type StepProps } from "./shared";

const BANDS: [number, number, string][] = [
  [0, 0.5, "< 50%"],
  [0.5, 0.7, "50–70%"],
  [0.7, 0.9, "70–90%"],
  [0.9, 0.99, "90–99%"],
  [0.99, 1.0001, "≥ 99%"],
];

function rolesBy(rows: Row[], direction: string, roleCol: string) {
  const list = rows.filter((r) => r.direction === direction);
  const total = sum(list, "amount");
  return [...groupBy(list, (r) => String(r[roleCol]))]
    .map(([role, items]) => ({ role, amount: sum(items, "amount"), count: items.length, share: sum(items, "amount") / total }))
    .sort((a, b) => b.amount - a.amount);
}

type Pick = "rule" | "uncertain" | "largest";

/** Pipeline step 4 is shared: part "model" is M2 (classifier + calibration), part "rules" is M3 (rule overlay). */
export default function Step04({ trace, meta, onOpenTxn, part }: StepProps) {
  const rows = useTxnRows(trace);
  const roles = meta?.roles;
  const model = part !== "rules";
  const rules = part !== "model";
  const roleCol = part === "model" ? "s04_calibrated_top_role" : "s04_top_role";
  const pCol = part === "model" ? "s04_calibrated_top_p" : "s04_top_p";
  const [pick, setPick] = useState<Pick>(part === "model" ? "uncertain" : "rule");

  const credit = useMemo(() => rolesBy(rows, "CREDIT", roleCol), [rows, roleCol]);
  const debit = useMemo(() => rolesBy(rows, "DEBIT", roleCol), [rows, roleCol]);
  const bands = useMemo(
    () =>
      BANDS.map(([lo, hi, label]) => {
        const items = rows.filter((r) => (r[pCol] as number) >= lo && (r[pCol] as number) < hi);
        return { label, count: items.length, amount: sum(items, "amount") };
      }),
    [rows, pCol],
  );
  const totalAmount = sum(rows, "amount");
  const ruleCounts = useMemo(() => {
    const counts = new Map<string, { count: number; amount: number }>();
    for (const r of rows) {
      for (const id of (r.s04_rules_applied as string[]) ?? []) {
        const c = counts.get(id) ?? { count: 0, amount: 0 };
        c.count += 1;
        c.amount += r.amount as number;
        counts.set(id, c);
      }
    }
    return [...counts].sort((a, b) => b[1].count - a[1].count);
  }, [rows]);
  const ruleDescriptions = useMemo(() => {
    const out: Record<string, string> = {};
    for (const t of Object.values(trace.roleTrace ?? {})) for (const a of t.rules) out[a.rule_id] ??= `${a.action} · ${a.description}`;
    return out;
  }, [trace.roleTrace]);
  const changedByRules = rows.filter((r) => r.s04_calibrated_top_role !== r.s04_top_role);
  const changedByCalibration = rows.filter((r) => r.s04_model_top_role !== r.s04_calibrated_top_role).length;

  const example = useMemo(() => {
    const byAmount = [...rows].sort((a, b) => (b.amount as number) - (a.amount as number));
    if (pick === "rule") return byAmount.find((r) => ((r.s04_rules_applied as string[]) ?? []).length > 0) ?? byAmount[0];
    if (pick === "uncertain") return [...rows].sort((a, b) => (b.amount as number) * (1 - (b[pCol] as number)) - (a.amount as number) * (1 - (a[pCol] as number)))[0];
    return byAmount[0];
  }, [rows, pick, pCol]);
  const rt = example ? trace.roleTrace?.[String(example.transaction_id)] : undefined;
  const stages = (
    [
      ["1 · Model (softmax of scores)", rt?.model, model],
      ["2 · Calibrated", rt?.calibrated, true],
      ["3 · After rule overlay", rt?.after_rules, rules],
    ] as const
  ).filter(([, , show]) => show);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader
          title={model ? "How a role probability is computed (Section 7)" : "How the rule overlay changes a distribution (Section 7.4)"}
          subtitle={
            model
              ? "Transparent log-linear baseline: every transaction gets a full distribution over roles, never a single hard label"
              : "Versioned high-precision rules encode bank and channel semantics the model must not override"
          }
        />
        <CardBody className="space-y-3">
          <Formula>
            {model && (
              <>
                score(r) = ln prior(r) + Σ evidence_weight(r) &nbsp;&nbsp;·&nbsp;&nbsp; evidence-gated roles (lender, EMI, capex, tax, owner, personal, internal …) get −3.0 when no evidence fires
                <br />
                P(r) = exp(score(r)) ÷ Σ exp(score) &nbsp;&nbsp;·&nbsp;&nbsp; over C01–C13 for credits, D01–D19 for debits
                <br />
                P_cal(r) ∝ P(r)^(1/T) &nbsp;&nbsp;·&nbsp;&nbsp; temperature T = 1 until fitted on adjudicated labels (identity)
              </>
            )}
            {model && rules && <br />}
            {rules && (
              <>
                rules R001–R012 act on the calibrated distribution: SET (only at ≥ 99.5% rule certainty) · MULTIPLY · RESTRICT, then renormalise
                {!model && (
                  <>
                    <br />
                    SET: P′ = the rule&apos;s role weights (e.g. EMI → D09 principal / D08 interest split) &nbsp;·&nbsp; a SET rule below 99.5% confidence is downgraded to MULTIPLY × 20
                    <br />
                    MULTIPLY: P′(r) ∝ max(P(r), 10⁻⁶) × factor(r) &nbsp;·&nbsp; RESTRICT: P′(r) ∝ P(r) for allowed roles, 0 otherwise &nbsp;·&nbsp; after a binding SET only further SET rules apply
                  </>
                )}
              </>
            )}
          </Formula>
          {model && (
            <Note>
              Evidence comes from the feature inputs above: channel family, lexicon matches in the narration, identifiers, counterparty recurrence, holder-name
              match and neighbourhood behaviour. Unknown roles (C13, D19) keep their mass when evidence is weak instead of being forced into a guess.
            </Note>
          )}
        </CardBody>
      </Card>

      <div className="grid gap-6 xl:grid-cols-2">
        {[
          { title: "Credits by most-likely role", items: credit },
          { title: "Debits by most-likely role", items: debit },
        ].map((g) => (
          <Card key={g.title}>
            <CardHeader
              title={g.title}
              subtitle={`Rupee amount of transactions whose top role is this role (${part === "model" ? "calibrated, before rules" : "after rules"})`}
            />
            <CardBody>
              <BarList
                format={inrShort}
                items={g.items.map((i) => ({
                  key: i.role,
                  label: roleLabel(roles, i.role),
                  value: i.amount,
                  color: roleColor(i.role),
                  sub: `${i.count.toLocaleString("en-IN")} · ${pct(i.share)}`,
                }))}
              />
            </CardBody>
          </Card>
        ))}
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader title="How certain are the roles?" subtitle="Top-role probability bands, by count and by rupee amount" />
          <CardBody className="space-y-3">
            {bands.map((b) => (
              <div key={b.label} className="grid grid-cols-[4.5rem_1fr_8rem] items-center gap-3 text-xs">
                <span className="font-mono text-ink-300">{b.label}</span>
                <div className="h-2 overflow-hidden rounded-full bg-white/[0.05]">
                  <div className="h-full rounded-full bg-gradient-to-r from-sky-400 to-emerald-400" style={{ width: `${(b.amount / totalAmount) * 100}%` }} />
                </div>
                <span className="text-right text-ink-300 tabular">
                  {b.count.toLocaleString("en-IN")} · {pct(b.amount / totalAmount)}
                </span>
              </div>
            ))}
          </CardBody>
        </Card>

        {rules ? (
          <Card>
            <CardHeader
              title="Rules that fired"
              subtitle={`${rows.filter((r) => ((r.s04_rules_applied as string[]) ?? []).length).length.toLocaleString("en-IN")} transactions adjusted; ${changedByRules.length} had their top role changed by a rule`}
            />
            <CardBody className="space-y-2">
              {ruleCounts.length === 0 && <Empty>No deterministic rule applied to this statement.</Empty>}
              {ruleCounts.map(([id, c]) => (
                <div key={id} className="rounded-lg bg-white/[0.02] px-3 py-2 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-mono font-semibold text-sky-200">{id}</span>
                    <span className="text-ink-300 tabular">
                      {c.count.toLocaleString("en-IN")} txns · {inr(c.amount)}
                    </span>
                  </div>
                  {ruleDescriptions[id] && <div className="mt-0.5 text-ink-400">{ruleDescriptions[id]}</div>}
                </div>
              ))}
            </CardBody>
          </Card>
        ) : (
          <Card>
            <CardHeader title="Calibration" subtitle="Temperature scaling per direction; it reshapes confidence without reordering roles when T is shared" />
            <CardBody className="space-y-3">
              <Formula>P_cal(r) = P(r)^(1/T) ÷ Σ P^(1/T)</Formula>
              <Note>
                The shipped artifact uses T = 1 for credits and debits (identity) until it is fitted on adjudicated labels, so calibrated and raw model
                distributions match. Top role changed by calibration on {changedByCalibration} transactions.
              </Note>
            </CardBody>
          </Card>
        )}
      </div>

      {part === "rules" && changedByRules.length > 0 && (
        <Card>
          <CardHeader title={`Top roles overridden by rules (${changedByRules.length})`} subtitle="Calibrated model top role → top role after the overlay" />
          <CardBody className="space-y-0.5">
            {changedByRules.slice(0, 40).map((r) => (
              <TxnLink key={String(r.transaction_id)} row={r} onOpen={onOpenTxn}>
                <span className="font-mono" style={{ color: roleColor(String(r.s04_calibrated_top_role)) }}>{String(r.s04_calibrated_top_role)}</span>
                {" → "}
                <span className="font-mono" style={{ color: roleColor(String(r.s04_top_role)) }}>{String(r.s04_top_role)}</span>
                <span className="ml-2 text-ink-400">{((r.s04_rules_applied as string[]) ?? []).join(", ")} · {String(r.normalized_narration ?? "")}</span>
              </TxnLink>
            ))}
          </CardBody>
        </Card>
      )}

      <Card>
        <CardHeader
          title={part === "rules" ? "One transaction through the overlay" : "One transaction through the role model"}
          subtitle={stages.map(([t]) => t.replace(/^\d · /, "")).join(" → ")}
          right={
            <div className="flex gap-1">
              {(
                [
                  ["rule", "Largest with a rule"],
                  ["uncertain", "Largest uncertain"],
                  ["largest", "Largest overall"],
                ] as [Pick, string][]
              ).map(([id, label]) => (
                <button
                  key={id}
                  onClick={() => setPick(id)}
                  className={cx("rounded-lg px-2.5 py-1 text-[11px]", pick === id ? "bg-white/10 text-ink-100" : "text-ink-400 hover:text-ink-100")}
                >
                  {label}
                </button>
              ))}
            </div>
          }
        />
        <CardBody className="space-y-4">
          {example && <TxnLink row={example} onOpen={onOpenTxn} />}
          {!rt ? (
            <Empty>Stage-by-stage probabilities arrive with the final result.</Empty>
          ) : (
            <>
              <div className={cx("grid gap-6", stages.length === 3 ? "lg:grid-cols-3" : "lg:grid-cols-2")}>
                {stages.map(([title, probs]) => (
                  <div key={title}>
                    <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-ink-400">{title}</div>
                    <ProbBars probs={probs ?? {}} labels={roles} colorOf={roleColor} limit={5} />
                  </div>
                ))}
              </div>
              {rules && rt.rules.length > 0 && (
                <div className="space-y-1.5">
                  {rt.rules.map((a) => (
                    <div key={a.rule_id + a.action} className="flex flex-wrap items-center gap-2 text-xs">
                      <Badge tone="info">{a.rule_id}</Badge>
                      <Badge>{a.action}</Badge>
                      <span className="text-ink-300">{a.description}</span>
                      <span className="font-mono text-[11px] text-ink-400">
                        {Object.entries(a.roles).map(([r, v]) => `${r}:${v}`).join(" ")}
                      </span>
                    </div>
                  ))}
                </div>
              )}
              {rules && rt.rules.length === 0 && <Note>No rule fired on this transaction, so the overlay leaves the calibrated distribution unchanged.</Note>}
            </>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
