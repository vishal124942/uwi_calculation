"use client";

import { ArrowRight, FileCode2, FolderTree, Timer } from "lucide-react";
import { type ComponentType, useMemo, useState } from "react";
import {
  componentCode,
  componentColumns,
  componentHeadline,
  componentTables,
  componentTiming,
  KIND_LABEL,
  partView,
} from "@/lib/components";
import { ms } from "@/lib/format";
import { rowsOf, transactionRows, type TraceState } from "@/lib/trace";
import type { ComponentMeta, Meta } from "@/lib/types";
import DataTable from "./DataTable";
import type { View } from "./Sidebar";
import type { StepProps } from "./steps/shared";
import Step01 from "./steps/Step01";
import Step02 from "./steps/Step02";
import Step03 from "./steps/Step03";
import Step04 from "./steps/Step04";
import Step05 from "./steps/Step05";
import Step06 from "./steps/Step06";
import Step07 from "./steps/Step07";
import Step08 from "./steps/Step08";
import Step09 from "./steps/Step09";
import Step10 from "./steps/Step10";
import { Card, CardBody, cx, Empty, SectionHeading, Tabs } from "./ui";

const STEP_VIEWS: Record<string, ComponentType<StepProps>> = {
  step01_ingest_and_clean: Step01,
  step02_data_quality_gate: Step02,
  step03_transaction_evidence: Step03,
  step04_role_inference: Step04,
  step05_pairing_and_multi_account: Step05,
  step06_aggregation_archetype_cash: Step06,
  step07_risk_signals: Step07,
  step08_income_and_legal_attribution: Step08,
  step09_uncertainty_and_policy: Step09,
  step10_explain_and_audit: Step10,
};

const BASE_COLUMNS = ["transaction_id", "booking_date", "direction", "amount", "normalized_narration"];

type Tab = "calc" | "transactions" | "tables";

export function ComponentChip({ c, className }: { c: ComponentMeta; className?: string }) {
  return (
    <span
      className={cx(
        "inline-flex shrink-0 items-center justify-center rounded-md px-1.5 py-0.5 font-mono text-[10px] font-semibold",
        c.kind === "model" ? "bg-sky-400/10 text-sky-300 ring-1 ring-inset ring-sky-400/25" : "bg-white/[0.05] text-ink-300 ring-1 ring-inset ring-white/10",
        className,
      )}
    >
      {componentCode(c)}
    </span>
  );
}

export default function ComponentView({
  component: c,
  trace,
  meta,
  onOpenTxn,
  onView,
}: {
  component: ComponentMeta;
  trace: TraceState;
  meta: Meta | null;
  onOpenTxn: (id: string) => void;
  onView: (v: View) => void;
}) {
  const [tab, setTab] = useState<Tab>("calc");
  const [table, setTable] = useState<string | null>(null);
  const ready = c.steps.every((s) => trace.steps[s]);
  const owned = useMemo(() => componentColumns(c, trace), [c, trace]);
  const tables = useMemo(() => componentTables(c, trace), [c, trace]);
  const activeTable = tables.find((t) => t.name === table) ?? tables[0];
  const timing = componentTiming(meta, trace, c);

  const txnColumns = useMemo(() => [...new Set([...BASE_COLUMNS, ...owned])], [owned]);
  // txnVersion changes whenever a step merges new columns into the shared row map
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const txnRows = useMemo(() => transactionRows(trace), [trace.order, trace.txnVersion]);
  const otherColumns = useMemo(() => Object.keys(txnRows[0] ?? {}).filter((col) => !txnColumns.includes(col)), [txnRows, txnColumns]);
  const highlight = useMemo(() => new Set(owned), [owned]);
  const tableRows = useMemo(() => (activeTable ? rowsOf(activeTable.table) : []), [activeTable]);

  if (!ready) return <Empty>{c.id} has not run yet.</Empty>;

  return (
    <div className="rise space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <ComponentChip c={c} className="px-2 text-xs" />
            <span className="text-ink-300">{KIND_LABEL[c.kind]}</span>
            <span className="text-ink-400">{c.sections}</span>
            <span className="inline-flex items-center gap-1 text-ink-400" title="Engine time of the pipeline step(s) this component runs in">
              <Timer className="h-3 w-3" /> {ms(timing.ms)}
              {timing.sharedWith.length > 0 && <span>· pipeline step shared with {timing.sharedWith.join(", ")}</span>}
            </span>
          </div>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">
            {c.kind === "model" && <span className="mr-2 text-sky-300">{c.id}</span>}
            {c.name}
          </h1>
          <p className="mt-1 max-w-4xl text-sm text-ink-300">{componentHeadline(c, trace)}</p>
        </div>
        <Tabs<Tab>
          value={tab}
          onChange={setTab}
          tabs={[
            { id: "calc", label: "Calculations" },
            ...(owned.length ? [{ id: "transactions" as const, label: "Transactions", count: txnRows.length }] : []),
            ...(tables.length ? [{ id: "tables" as const, label: "Raw tables", count: tables.length }] : []),
          ]}
        />
      </div>

      <Card>
        <div className="grid gap-px overflow-hidden rounded-2xl bg-white/[0.05] md:grid-cols-[1fr_1fr_1.4fr]">
          <div className="bg-ink-900/90 px-5 py-4">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-400">{c.kind === "model" ? "Technique (spec §24.1)" : "Technique"}</div>
            <div className="mt-1 text-sm text-ink-100">{c.technique}</div>
          </div>
          <div className="bg-ink-900/90 px-5 py-4">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-400">{c.kind === "model" ? "Responsibility (spec §24.1)" : "Responsibility"}</div>
            <div className="mt-1 text-sm text-ink-100">{c.responsibility}</div>
          </div>
          <div className="space-y-2 bg-ink-900/90 px-5 py-4">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-400">Implemented by</div>
            <div className="flex items-center gap-1.5 font-mono text-[11px] text-ink-200" title="Code package of this component">
              <FolderTree className="h-3 w-3 text-ink-400" /> se_income_engine/{c.package}/
            </div>
            {c.modules.map((m) => (
              <div key={m.name} className="min-w-0 pl-4">
                <div className="flex flex-wrap items-center gap-x-2 font-mono text-xs text-sky-200">
                  <FileCode2 className="h-3 w-3" /> {m.name}.py
                  <span className="text-[10px] text-ink-400" title="Pipeline checkpoint at which this module's work is complete">
                    runs by {m.step}
                  </span>
                </div>
                <div className="mt-0.5 text-[11px] leading-snug text-ink-400">{m.doc}</div>
              </div>
            ))}
          </div>
        </div>
      </Card>

      {tab === "calc" &&
        c.steps.map((step) => {
          const StepPart = STEP_VIEWS[step];
          const mods = c.modules.filter((m) => m.step === step);
          return (
            <div key={step} className="space-y-4">
              {c.steps.length > 1 && (
                <SectionHeading hint={mods.map((m) => `${m.name}.py`).join(" · ")}>
                  {step === c.steps[c.steps.length - 1] ? `${c.id} ${c.name}` : "Feature inputs"} · {step}
                </SectionHeading>
              )}
              <StepPart data={trace.steps[step]} trace={trace} meta={meta} onOpenTxn={onOpenTxn} part={partView(c.id, step).part} />
            </div>
          );
        })}

      {tab === "transactions" && owned.length > 0 && (
        <Card>
          <div className="p-5">
            <p className="mb-3 text-xs text-ink-300">
              The transaction table with the {owned.length} columns {c.kind === "model" ? c.id : c.name} adds (highlighted). Filter any column from its header
              menu, show the other {otherColumns.length} columns from <span className="text-ink-100">Columns</span>, open{" "}
              <span className="text-ink-100">Full panel</span> for a full-screen view, and click a row to follow that transaction through every component.
            </p>
            <DataTable
              key={otherColumns.length}
              columns={[...txnColumns, ...otherColumns]}
              hiddenColumns={otherColumns}
              rows={txnRows}
              highlight={highlight}
              height={600}
              onRowClick={(r) => onOpenTxn(String(r.transaction_id))}
              downloadName={`${c.id}_transactions`}
              title={`${componentCode(c)} ${c.name} · transactions`}
            />
          </div>
        </Card>
      )}

      {tab === "tables" && activeTable && (
        <Card>
          <CardBody>
            <div className="mb-4 flex flex-wrap gap-2">
              {tables.map((t) => (
                <button
                  key={t.name}
                  onClick={() => setTable(t.name)}
                  className={cx(
                    "rounded-lg border px-3 py-1.5 font-mono text-[11px] transition",
                    t.name === activeTable.name ? "border-sky-400/40 bg-sky-400/10 text-sky-200" : "border-white/[0.08] text-ink-300 hover:text-ink-100",
                  )}
                >
                  {t.name}.csv <span className="ml-1 text-ink-400">{t.table.rows.length}</span>
                </button>
              ))}
            </div>
            <DataTable
              key={activeTable.name}
              columns={activeTable.table.columns}
              rows={tableRows}
              height={560}
              rowKey={activeTable.table.columns[0]}
              downloadName={`${c.id}_${activeTable.name}`}
              title={`${componentCode(c)} ${c.name} · ${activeTable.name}.csv`}
            />
          </CardBody>
        </Card>
      )}

      <Pager current={c} meta={meta} trace={trace} onView={onView} />
    </div>
  );
}

function Pager({ current, meta, trace, onView }: { current: ComponentMeta; meta: Meta | null; trace: TraceState; onView: (v: View) => void }) {
  const list = meta?.components ?? [];
  const i = list.findIndex((c) => c.id === current.id);
  const prev = list[i - 1];
  const next = list[i + 1];
  const nextReady = next && next.steps.every((s) => trace.steps[s]);
  return (
    <div className="flex justify-between gap-4 pt-2">
      {prev ? (
        <button onClick={() => onView(prev.id)} className="rounded-xl border border-white/[0.07] px-4 py-3 text-left text-xs hover:bg-white/[0.03]">
          <div className="text-ink-400">← {componentCode(prev)}</div>
          <div className="text-ink-100">{prev.name}</div>
        </button>
      ) : (
        <span />
      )}
      {next && nextReady && (
        <button onClick={() => onView(next.id)} className="group rounded-xl border border-white/[0.07] px-4 py-3 text-right text-xs hover:bg-white/[0.03]">
          <div className="inline-flex items-center gap-1 text-ink-400">
            {componentCode(next)} <ArrowRight className="h-3 w-3 transition group-hover:translate-x-0.5" />
          </div>
          <div className="text-ink-100">{next.name}</div>
        </button>
      )}
    </div>
  );
}
