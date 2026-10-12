"use client";

import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell as RCell,
  ComposedChart,
  Line,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { featureName, inr, inrShort, pct } from "@/lib/format";
import type { BridgeLine } from "@/lib/types";
import { cx } from "./ui";

export const AXIS = { stroke: "#3d4a60", tick: { fill: "#94a1b6", fontSize: 11 }, tickLine: false } as const;
export const GRID = { stroke: "#ffffff", strokeOpacity: 0.05, vertical: false } as const;
export const TOOLTIP = {
  contentStyle: {
    background: "#0f1622",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: 12,
    fontSize: 12,
    color: "#e6eaf1",
  },
  labelStyle: { color: "#c3cbd8", fontWeight: 600, marginBottom: 4 },
  itemStyle: { padding: 0 },
  cursor: { fill: "rgba(255,255,255,0.04)" },
} as const;

const KIND_COLOR: Record<BridgeLine["kind"], string> = {
  TOTAL: "#94a1b6",
  DEDUCTION: "#fb7185",
  SUBTOTAL: "#38bdf8",
  ADJUSTMENT: "#fbbf24",
  RESULT: "#34d399",
  MEMO: "#66748b",
  POLICY: "#a78bfa",
};

function shortLine(line: string): string {
  const abbreviation = line.match(/\(([A-Z]{2,5})\)/);
  if (abbreviation) return abbreviation[1];
  return line
    .replace(/^Less: /, "− ")
    .replace("other non-operating, pass-through and uncertain credits", "non-operating")
    .replace("internal / own-account transfers", "internal")
    .replace("financing credits", "financing")
    .replace("Gross banking credits", "Gross credits")
    .replace("Cycle / liquidation normalisation", "Cycle adj.")
    .replace("Robust-centre and trend normalisation", "Robust centre")
    .replace("Maintenance capex reserve", "Capex reserve")
    .replace("Permitted adjustments", "Permitted adj.");
}

function waterfallBars(bridge: BridgeLine[]) {
  const bars = [];
  let running = 0;
  for (const b of bridge) {
    if (b.kind === "MEMO" || (b.kind === "ADJUSTMENT" && Math.abs(b.monthly_amount) < 0.005)) continue;
    let range: [number, number];
    if (b.kind === "DEDUCTION" || b.kind === "ADJUSTMENT") {
      const next = running + b.monthly_amount;
      range = [Math.min(running, next), Math.max(running, next)];
      running = next;
    } else {
      range = [Math.min(0, b.monthly_amount), Math.max(0, b.monthly_amount)];
      if (b.kind !== "POLICY") running = b.monthly_amount;
    }
    bars.push({ name: shortLine(b.line), full: b.line, kind: b.kind, value: b.monthly_amount, range, note: b.note });
  }
  return bars;
}

/** Gross credits -> EOC -> ROC -> CAOCG -> SBCI -> UWI as floating range bars. */
export function BridgeWaterfall({ bridge, height = 340 }: { bridge: BridgeLine[]; height?: number }) {
  const data = waterfallBars(bridge);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 16, right: 8, bottom: 4, left: 8 }}>
        <CartesianGrid {...GRID} />
        <XAxis
          dataKey="name"
          {...AXIS}
          interval={0}
          height={64}
          angle={-32}
          textAnchor="end"
          tick={{ ...AXIS.tick, fontSize: 10 }}
        />
        <YAxis {...AXIS} tickFormatter={inrShort} width={72} />
        <ReferenceLine y={0} stroke="#3d4a60" />
        <Tooltip
          {...TOOLTIP}
          formatter={(_v, _n, item) => [inr(item.payload.value, 2), item.payload.kind]}
          labelFormatter={(_l, items) => items?.[0]?.payload.full ?? ""}
        />
        <Bar dataKey="range" radius={[4, 4, 4, 4]} maxBarSize={46} isAnimationActive>
          {data.map((d) => (
            <RCell key={d.full} fill={KIND_COLOR[d.kind]} fillOpacity={d.kind === "TOTAL" ? 0.55 : 0.9} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export interface SeriesSpec {
  key: string;
  label: string;
  color: string;
  type: "bar" | "line" | "area";
  dashed?: boolean;
}

export function SeriesChart({
  data,
  xKey,
  series,
  height = 300,
  formatY = inrShort,
  formatValue = (v: number) => inr(v),
  stacked,
  referenceY,
}: {
  data: object[];
  xKey: string;
  series: SeriesSpec[];
  height?: number;
  formatY?: (v: number) => string;
  formatValue?: (v: number) => string;
  stacked?: boolean;
  referenceY?: { y: number; label: string; color: string }[];
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ top: 12, right: 12, bottom: 0, left: 8 }}>
        <defs>
          {series
            .filter((s) => s.type === "area")
            .map((s) => (
              <linearGradient key={s.key} id={`grad-${s.key}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={s.color} stopOpacity={0.35} />
                <stop offset="100%" stopColor={s.color} stopOpacity={0} />
              </linearGradient>
            ))}
        </defs>
        <CartesianGrid {...GRID} />
        <XAxis dataKey={xKey} {...AXIS} minTickGap={16} />
        <YAxis {...AXIS} tickFormatter={formatY} width={72} />
        <Tooltip {...TOOLTIP} formatter={(v, name) => [formatValue(Number(v)), name]} />
        <ReferenceLine y={0} stroke="#3d4a60" />
        {referenceY?.map((r) => (
          <ReferenceLine key={r.label} y={r.y} stroke={r.color} strokeDasharray="4 4" label={{ value: r.label, fill: r.color, fontSize: 10, position: "insideTopRight" }} />
        ))}
        {series.map((s) =>
          s.type === "bar" ? (
            <Bar key={s.key} dataKey={s.key} name={s.label} fill={s.color} fillOpacity={0.8} radius={[3, 3, 0, 0]} maxBarSize={28} stackId={stacked ? "a" : undefined} />
          ) : s.type === "area" ? (
            <Area key={s.key} dataKey={s.key} name={s.label} stroke={s.color} fill={`url(#grad-${s.key})`} strokeWidth={2} type="monotone" dot={false} />
          ) : (
            <Line key={s.key} dataKey={s.key} name={s.label} stroke={s.color} strokeWidth={2} strokeDasharray={s.dashed ? "5 4" : undefined} type="monotone" dot={{ r: 2.5 }} />
          ),
        )}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export function Legend({ items }: { items: { label: string; color: string; dashed?: boolean }[] }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1">
      {items.map((i) => (
        <span key={i.label} className="inline-flex items-center gap-1.5 text-[11px] text-ink-300">
          <span className={cx("inline-block h-0.5 w-3.5 rounded", i.dashed && "border-t border-dashed")} style={{ background: i.dashed ? "transparent" : i.color, borderColor: i.color }} />
          {i.label}
        </span>
      ))}
    </div>
  );
}

export function ConfidenceRadar({ dims, height = 300 }: { dims: Record<string, number>; height?: number }) {
  const data = Object.entries(dims).map(([k, v]) => ({ dim: k.slice(0, 4), label: featureName(k).label, value: v }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <RadarChart data={data} outerRadius="72%">
        <PolarGrid stroke="#ffffff" strokeOpacity={0.08} />
        <PolarAngleAxis dataKey="dim" tick={{ fill: "#94a1b6", fontSize: 11 }} />
        <PolarRadiusAxis domain={[0, 1]} tick={false} axisLine={false} />
        <Tooltip {...TOOLTIP} formatter={(v) => [pct(Number(v)), "score"]} labelFormatter={(_l, items) => items?.[0]?.payload.label ?? ""} />
        <Radar dataKey="value" stroke="#38bdf8" fill="#38bdf8" fillOpacity={0.25} strokeWidth={2} />
      </RadarChart>
    </ResponsiveContainer>
  );
}

/** Lower / central / upper interval with the policy-selected UWI marker. */
export function IntervalBand({
  lower,
  central,
  upper,
  uwi,
  lowerBeforeAllowance,
}: {
  lower: number;
  central: number;
  upper: number;
  uwi: number | null;
  lowerBeforeAllowance?: number | null;
}) {
  const lo = Math.min(lower, uwi ?? lower, lowerBeforeAllowance ?? lower);
  const span = Math.max(upper - lo, 1);
  const min = lo - span * 0.12;
  const max = upper + span * 0.12;
  const x = (v: number) => `${((v - min) / (max - min)) * 100}%`;
  const markers = [
    { v: lower, label: "Lower bound", color: "#fb7185", top: true },
    { v: central, label: "Central (SBCI)", color: "#34d399", top: true },
    { v: upper, label: "Upper bound", color: "#38bdf8", top: true },
    ...(uwi !== null ? [{ v: uwi, label: "UWI", color: "#a78bfa", top: false }] : []),
    ...(lowerBeforeAllowance && Math.abs(lowerBeforeAllowance - lower) > 0.5
      ? [{ v: lowerBeforeAllowance, label: "P-lower before allowance", color: "#fbbf24", top: false }]
      : []),
  ];
  return (
    <div className="relative h-36 select-none">
      <div className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-white/10" />
      <div
        className="absolute top-1/2 h-3 -translate-y-1/2 rounded-full bg-gradient-to-r from-rose-400/40 via-emerald-400/40 to-sky-400/40"
        style={{ left: x(lower), width: `calc(${x(upper)} - ${x(lower)})` }}
      />
      {markers.map((m) => (
        <div key={m.label} className="absolute top-1/2 h-0 w-0" style={{ left: x(m.v) }}>
          <div className="absolute -top-3 -left-px h-6 w-0.5 rounded" style={{ background: m.color }} />
          <div
            className={cx("absolute left-0 -translate-x-1/2 whitespace-nowrap text-center", m.top ? "bottom-4" : "top-4")}
          >
            <div className="text-[10px] uppercase tracking-wider" style={{ color: m.color }}>{m.label}</div>
            <div className="font-mono text-xs text-ink-100 tabular">{inr(m.v)}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

export function Histogram({
  values,
  bins = 30,
  markers = [],
  height = 220,
}: {
  values: number[];
  bins?: number;
  markers?: { x: number; label: string; color: string }[];
  height?: number;
}) {
  if (!values.length) return null;
  const min = Math.min(...values, ...markers.map((m) => m.x));
  const max = Math.max(...values, ...markers.map((m) => m.x));
  const width = (max - min) / bins || 1;
  const counts = Array.from({ length: bins }, (_, i) => ({ x: min + width * (i + 0.5), count: 0 }));
  for (const v of values) counts[Math.min(bins - 1, Math.floor((v - min) / width))].count += 1;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={counts} margin={{ top: 24, right: 12, bottom: 0, left: 0 }} barCategoryGap={1}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="x" type="number" domain={[min - width, max + width]} {...AXIS} tickFormatter={inrShort} />
        <YAxis {...AXIS} width={32} allowDecimals={false} />
        <Tooltip {...TOOLTIP} formatter={(v) => [v, "bootstrap draws"]} labelFormatter={(l) => `≈ ${inr(Number(l))}`} />
        <Bar dataKey="count" fill="#38bdf8" fillOpacity={0.45} barSize={Math.max(2, 600 / bins - 2)} />
        {markers.map((m, i) => (
          <ReferenceLine
            key={m.label}
            x={m.x}
            stroke={m.color}
            strokeWidth={2}
            label={{ value: m.label, fill: m.color, fontSize: 10, position: i % 2 ? "insideTopLeft" : "insideTopRight" }}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Ranked horizontal bars (plain divs: crisper than SVG for long labelled lists). */
export function BarList({
  items,
  format = inr,
  max,
}: {
  items: { key: string; label: string; value: number; color: string; sub?: string }[];
  format?: (v: number) => string;
  max?: number;
}) {
  const top = max ?? Math.max(...items.map((i) => Math.abs(i.value)), 1);
  return (
    <div className="space-y-2">
      {items.map((i) => (
        <div key={i.key}>
          <div className="mb-1 flex items-baseline justify-between gap-3 text-xs">
            <span className="truncate text-ink-200">
              <span className="mr-1.5 font-mono font-semibold" style={{ color: i.color }}>{i.key}</span>
              {i.label}
            </span>
            <span className="shrink-0 font-mono text-ink-100 tabular">
              {format(i.value)}
              {i.sub && <span className="ml-2 text-ink-400">{i.sub}</span>}
            </span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.05]">
            <div className="h-full rounded-full" style={{ width: `${(Math.abs(i.value) / top) * 100}%`, background: i.color }} />
          </div>
        </div>
      ))}
    </div>
  );
}
