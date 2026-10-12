"use client";

import { useMemo } from "react";
import { cellText, inr } from "@/lib/format";
import { rowsOf } from "@/lib/trace";
import type { BridgeLine } from "@/lib/types";
import type { StepProps } from "./shared";
import DataTable from "../DataTable";
import { BridgeWaterfall, Legend } from "../charts";
import { Badge, Card, CardBody, CardHeader, cx, Empty, KeyValueGrid } from "../ui";

const KIND_TONE: Record<string, string> = {
  TOTAL: "text-ink-200",
  DEDUCTION: "text-rose-300",
  SUBTOTAL: "text-sky-300 font-semibold",
  ADJUSTMENT: "text-amber-300",
  RESULT: "text-emerald-300 font-semibold",
  MEMO: "text-ink-400",
  POLICY: "text-violet-300 font-semibold",
};

export default function Step10({ data, trace }: StepProps) {
  const bridge = useMemo(() => rowsOf(data.tables.step10_bridge) as unknown as BridgeLine[], [data]);
  const drivers = rowsOf(data.tables.step10_drivers);
  const features = useMemo(() => rowsOf(data.tables.step10_feature_vector), [data]);
  const reasons = trace.result?.reasons ?? [];

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader
          title="Underwriter bridge (Section 28.1)"
          subtitle="Computed from the same audited aggregates as the estimate; each subtotal equals the previous subtotal plus the lines between them"
        />
        <CardBody className="grid gap-6 xl:grid-cols-[1.3fr_1fr]">
          <div>
            <Legend
              items={[
                { label: "Total", color: "#94a1b6" },
                { label: "Deduction", color: "#fb7185" },
                { label: "Subtotal", color: "#38bdf8" },
                { label: "Adjustment", color: "#fbbf24" },
                { label: "SBCI", color: "#34d399" },
                { label: "UWI", color: "#a78bfa" },
              ]}
            />
            <BridgeWaterfall bridge={bridge} height={380} />
          </div>
          <div>
            {bridge.map((b) => (
              <div key={b.line} className={cx("flex items-baseline justify-between gap-3 border-b border-white/[0.04] py-1.5 text-xs", b.kind === "SUBTOTAL" && "mt-1")}>
                <span className={KIND_TONE[b.kind]}>
                  {b.line}
                  {b.note && <span className="ml-2 font-normal text-[11px] text-ink-400">{b.note}</span>}
                </span>
                <span className={cx("font-mono tabular", KIND_TONE[b.kind])}>{inr(b.monthly_amount, 2)}</span>
              </div>
            ))}
          </div>
        </CardBody>
      </Card>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader title="Reason codes (Section 28.2)" subtitle="RC01–RC10 fire on fixed thresholds over the audited features" />
          <CardBody className="space-y-3">
            {reasons.length === 0 && <Empty>No reason code fired for this analysis.</Empty>}
            {reasons.map((r) => (
              <div key={r.code} className="rounded-xl border border-amber-400/20 bg-amber-400/[0.05] px-4 py-3">
                <div className="flex items-center gap-2">
                  <Badge tone="warn">{r.code}</Badge>
                  <span className="text-sm font-semibold">{r.reason}</span>
                </div>
                <div className="mt-1 text-xs text-ink-300">{r.meaning}</div>
                <div className="mt-2">
                  <KeyValueGrid columns={1} data={r.evidence} />
                </div>
              </div>
            ))}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Key drivers" subtitle="Headline features an underwriter reads first" />
          <CardBody>
            <KeyValueGrid
              columns={1}
              data={Object.fromEntries(drivers.map((d) => [String(d.driver), d.probability != null ? `${cellText(d.value)} (p ${cellText(d.probability)})` : d.value]))}
            />
            <div className="mt-6 text-[11px] font-semibold uppercase tracking-wider text-ink-400">Model versions (audit trail)</div>
            <div className="mt-2">
              <KeyValueGrid columns={1} data={trace.result?.model_versions ?? {}} />
            </div>
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader title={`Feature vector (Section 23): ${features.length} registry features`} subtitle="Every feature is versioned and traceable to the module that computes it" />
        <CardBody>
          <DataTable columns={["feature", "value"]} rows={features} rowKey="feature" height={420} downloadName="feature_vector" searchPlaceholder="Search features (e.g. BAL, WC06, F04)…" />
        </CardBody>
      </Card>
    </div>
  );
}
