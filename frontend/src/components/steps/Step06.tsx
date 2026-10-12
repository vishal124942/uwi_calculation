"use client";

import { useMemo } from "react";
import { fixed, inr, inrShort, pct } from "@/lib/format";
import { roleColor } from "@/lib/roles";
import { rowsOf, sectionsOf } from "@/lib/trace";
import type { Row } from "@/lib/types";
import { BarList, Legend, SeriesChart } from "../charts";
import { Badge, CalcLine, Card, CardBody, CardHeader, Formula, KeyValueGrid, Note } from "../ui";
import { TxnLink, useTxnRows, type StepProps } from "./shared";

const CREDIT_BUCKETS: [string, string, string][] = [
  ["eoc_credit", "Operating collections (EOC)", "C01"],
  ["financing_in", "Financing", "C05"],
  ["internal_in", "Internal / own transfers", "C04"],
  ["owner_capital_in", "Owner capital", "C06"],
  ["personal_in", "Personal / family", "C11"],
  ["pass_through_in", "Pass-through", "C12"],
  ["refund_in", "Refund / reversal", "C08"],
  ["interest_in", "Interest", "C10"],
  ["investment_in", "Asset / investment realisation", "C07"],
  ["statutory_refund_in", "Statutory refund", "C09"],
  ["unknown_in", "Unknown", "C13"],
];

const DEBIT_BUCKETS: [string, string, string][] = [
  ["direct_cost", "Direct purchase cost", "D01"],
  ["payroll", "Payroll / labour", "D02"],
  ["rent", "Rent / occupancy", "D03"],
  ["utilities", "Utilities", "D04"],
  ["logistics", "Logistics / freight", "D05"],
  ["other_opex", "Other opex", "D06"],
  ["statutory", "Statutory", "D07"],
  ["bank_fee", "Bank fees", "D18"],
  ["business_cash_withdrawal", "Business cash withdrawal", "D16"],
  ["owner_draw", "Owner draw", "D12"],
  ["personal_expense", "Personal expense", "D13"],
  ["internal_out", "Internal / own transfers", "D14"],
  ["debt_interest", "Debt interest", "D08"],
  ["debt_principal", "Debt principal", "D09"],
  ["capex", "Capex", "D10"],
  ["maintenance_capex", "Maintenance capex", "D11"],
  ["pass_through_out", "Pass-through", "D17"],
  ["refund_out", "Refund / reversal", "D15"],
  ["unknown_out", "Unknown", "D19"],
];

function bucketsOf(row: Row): Record<string, number> {
  return Object.fromEntries(
    Object.entries(row)
      .filter(([k, v]) => k.startsWith("s06_") && typeof v === "number" && v > 0.005 && !["s06_p_operating", "s06_role_uncertainty", "s06_cash_business_probability"].includes(k))
      .map(([k, v]) => [k.replace("s06_", ""), v as number]),
  );
}

/** Pipeline step 6 is shared: part "ledger" is the economic ledger (Sections 10–12), part "archetype" is M5. */
export default function Step06({ data, trace, meta, onOpenTxn, part }: StepProps) {
  const rows = useTxnRows(trace);
  const monthly = useMemo(() => rowsOf(data.tables.step06_monthly_totals), [data]);
  const windows = useMemo(() => rowsOf(data.tables.step06_window_totals), [data]);
  const archetype = sectionsOf(data.tables.step06_archetype);
  const passThrough = sectionsOf(data.tables.step06_pass_through_summary).pass_through ?? {};
  const full = windows[windows.length - 1];
  const months = (full?.months as number) || 1;
  const m = (k: string) => ((full?.[k] as number) ?? 0) / months;

  const credit = useMemo(() => [...rows].filter((r) => r.direction === "CREDIT").sort((a, b) => (b.amount as number) - (a.amount as number))[0], [rows]);
  const debit = useMemo(() => [...rows].filter((r) => r.direction === "DEBIT").sort((a, b) => (b.amount as number) - (a.amount as number))[0], [rows]);
  const archetypeProbs = (archetype.probability ?? {}) as Record<string, number>;
  const selected = String(archetype.selected?.archetype ?? "");
  const top = Object.entries(archetypeProbs).sort((a, b) => b[1] - a[1])[0];

  const archetypeCard = (
    <Card>
      <CardHeader
        title="Business archetype (Section 9)"
        subtitle="Softmax over archetype scores from account-level ledger features; below 35% the business is reported as A09 (unclassified)"
        right={<Badge tone="policy">{selected} {meta?.archetypes[selected]}</Badge>}
      />
      <CardBody className="space-y-4">
        <BarList
          format={(v) => pct(v)}
          max={1}
          items={Object.entries(archetypeProbs)
            .sort((a, b) => b[1] - a[1])
            .map(([k, v]) => ({ key: k, label: meta?.archetypes[k] ?? k, value: v, color: k === selected ? "#a78bfa" : "#3d4a60" }))}
        />
        {part === "archetype" && (
          <>
            <Formula>
              score(A01–A08) = Σ feature rules over ledger shares, retention and channel mix &nbsp;·&nbsp; score(A09) = 1.0
              <br />
              P = softmax(score) over A01–A09 &nbsp;·&nbsp; selected = argmax if max P ≥ 0.35, otherwise A09 (unclassified)
            </Formula>
            {top && (
              <div className="rounded-xl bg-white/[0.02] px-4 py-2">
                <CalcLine label={`most likely: ${top[0]} ${meta?.archetypes[top[0]] ?? ""}`} value={pct(top[1], 2)} />
                <CalcLine op="≥" label="classification floor" value="35.00%" note={top[1] >= 0.35 ? "met" : "not met"} />
                <CalcLine op="=" label="selected archetype" value={`${selected} ${meta?.archetypes[selected] ?? ""}`} emphasis />
              </div>
            )}
            <Note>
              The archetype feeds the cash-eligibility model in the economic ledger, the cycle engine (M6), coverage risk and the M8 archetype-confidence
              dimension CF09.
            </Note>
          </>
        )}
        <KeyValueGrid data={archetype.feature ?? {}} />
      </CardBody>
    </Card>
  );

  if (part === "archetype") return <div className="space-y-6">{archetypeCard}</div>;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader title="The economic ledger (Sections 10–11)" subtitle="Every transaction is split across role buckets in proportion to its role probabilities; nothing is classified all-or-nothing" />
        <CardBody className="space-y-3">
          <Formula>
            credit · EOC contribution = amount × P_operating, &nbsp; P_operating = P(C01) + P(C02) + cash_eligibility × P(C03)
            <br />
            debit · COR contribution = amount × P(core roles: D01–D06, plus D07 statutory, D18 fees, D16 business cash per income parameters)
            <br />
            any other bucket = amount × P(role) &nbsp;·&nbsp; one-off large debits that are probably not operating go to non_recurring_cor (a downside allowance in M8)
            <br />
            window · EOC = Σ EOC + max(0, pass_through_in − pass_through_out) &nbsp;·&nbsp; COR = Σ COR &nbsp;·&nbsp; ROC = EOC − COR &nbsp;·&nbsp; monthly = total ÷ covered months
          </Formula>
        </CardBody>
      </Card>

      <div className="grid gap-6 xl:grid-cols-3">
        {[
          { title: "Largest credit", row: credit, main: "eoc_credit", p: credit?.s06_p_operating, pLabel: "P_operating" },
          { title: "Largest debit", row: debit, main: "cor_debit", p: debit ? ((debit.s06_cor_debit as number) ?? 0) / (debit.amount as number) : 0, pLabel: "P(core opex)" },
        ].map(({ title, row, main, p, pLabel }) =>
          row ? (
            <Card key={title}>
              <CardHeader title={`Worked example: ${title.toLowerCase()}`} />
              <CardBody className="space-y-3">
                <TxnLink row={row} onOpen={onOpenTxn} />
                <div className="rounded-xl bg-white/[0.02] px-4 py-2">
                  <CalcLine label="amount" value={inr(row.amount, 2)} />
                  <CalcLine op="×" label={pLabel} value={fixed(p, 4)} />
                  <CalcLine op="=" label={main === "eoc_credit" ? "EOC contribution" : "COR contribution"} value={inr(row[`s06_${main}`] ?? 0, 2)} emphasis />
                </div>
                <div className="text-[11px] text-ink-400">All buckets this row feeds:</div>
                <KeyValueGrid columns={1} data={bucketsOf(row)} format={(_k, v) => inr(v, 2)} />
              </CardBody>
            </Card>
          ) : null,
        )}
        <Card>
          <CardHeader title="Full period, monthly equivalent" subtitle={full ? `${String(full.start)} → ${String(full.end)} · ${fixed(months, 2)} months covered` : undefined} />
          <CardBody>
            <div className="rounded-xl bg-white/[0.02] px-4 py-2">
              <CalcLine label="Σ EOC contributions ÷ months" value={inr(m("eoc_credit"), 2)} />
              <CalcLine op="+" label="retained pass-through" value={inr(m("retained_pass_through"), 2)} />
              <CalcLine op="=" label="EOC" value={inr(m("eoc"), 2)} emphasis />
              <CalcLine op="−" label="COR" value={inr(m("cor"), 2)} />
              <CalcLine op="=" label="ROC (raw operating cash generation)" value={inr(m("roc"), 2)} emphasis />
            </div>
            <Note>
              Gross credits were {inr(m("gross_credits"))} / month, so {pct(m("eoc") / m("gross_credits"))} of credits are expected operating collections.
            </Note>
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader title="Month by month" subtitle="Incomplete months (coverage < 90%) are excluded from the M7 robust centre" />
        <CardBody>
          <Legend
            items={[
              { label: "Gross credits", color: "#66748b" },
              { label: "EOC", color: "#34d399" },
              { label: "COR", color: "#fb7185" },
              { label: "ROC", color: "#38bdf8" },
            ]}
          />
          <SeriesChart
            data={monthly}
            xKey="month"
            series={[
              { key: "gross_credits", label: "Gross credits", color: "#66748b", type: "bar" },
              { key: "eoc", label: "EOC", color: "#34d399", type: "bar" },
              { key: "cor", label: "COR", color: "#fb7185", type: "bar" },
              { key: "roc", label: "ROC", color: "#38bdf8", type: "line" },
            ]}
          />
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Rolling windows" subtitle="Each window is aggregated on its own covered days, then converted to a monthly equivalent" />
        <CardBody className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-left text-ink-400">
              <tr className="border-b border-white/[0.06]">
                {["Window", "Period", "Months", "EOC / month", "COR / month", "ROC / month", "Operating credit ratio", "Direct cost ÷ EOC"].map((h, i) => (
                  <th key={h} className={`py-2 pr-4 font-medium ${i > 1 ? "text-right" : ""}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {windows.map((w) => {
                const mo = (w.months as number) || 1;
                return (
                  <tr key={String(w.window)} className="border-b border-white/[0.03]">
                    <td className="py-2 pr-4 font-mono text-ink-100">{String(w.window)}</td>
                    <td className="py-2 pr-4 text-ink-300">{String(w.start)} → {String(w.end)}</td>
                    <td className="py-2 pr-4 text-right font-mono tabular">{fixed(w.months, 2)}</td>
                    <td className="py-2 pr-4 text-right font-mono text-emerald-300 tabular">{inr((w.eoc as number) / mo)}</td>
                    <td className="py-2 pr-4 text-right font-mono text-rose-300 tabular">{inr((w.cor as number) / mo)}</td>
                    <td className="py-2 pr-4 text-right font-mono text-sky-300 tabular">{inr((w.roc as number) / mo)}</td>
                    <td className="py-2 pr-4 text-right font-mono tabular">{pct(w.IN05_OperatingCreditRatio)}</td>
                    <td className="py-2 text-right font-mono tabular">{pct(w.OUT06_DirectCostToEOC)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </CardBody>
      </Card>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader title="Where the credits went (monthly)" subtitle="Probability-weighted role buckets, full period" />
          <CardBody>
            <BarList
              format={inrShort}
              items={CREDIT_BUCKETS.filter(([k]) => m(k) > 0.5).map(([k, label, role]) => ({ key: role, label, value: m(k), color: roleColor(role) }))}
            />
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Where the debits went (monthly)" subtitle="Core operating roles form COR; owner draw, personal, debt and transfers do not" />
          <CardBody>
            <BarList
              format={inrShort}
              items={DEBIT_BUCKETS.filter(([k]) => m(k) > 0.5).map(([k, label, role]) => ({ key: role, label, value: m(k), color: roleColor(role) }))}
            />
          </CardBody>
        </Card>
      </div>

      <div className={part ? "" : "grid gap-6 xl:grid-cols-2"}>
        {!part && archetypeCard}
        <Card>
          <CardHeader title="Cash eligibility and pass-through (Section 12)" subtitle="Linked pass-through credits only count for the cash the business keeps" />
          <CardBody>
            <KeyValueGrid data={passThrough} columns={1} format={(k, v) => (/ratio|share/.test(k) ? pct(v) : /count/.test(k) ? String(v) : inr(v, 2))} />
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
