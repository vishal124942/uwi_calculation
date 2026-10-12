"use client";

import { useMemo, useState } from "react";
import { inr, inrShort, pct } from "@/lib/format";
import type { BridgeLine } from "@/lib/types";

const FRIENDLY: [RegExp, string][] = [
  [/^Gross banking credits/, "Money in (gross credits)"],
  [/financing credits/, "Loans and financing"],
  [/internal \/ own-account/, "Own-account transfers"],
  [/other non-operating/, "Non-operating and uncertain"],
  [/\(EOC\)/, "Operating collections"],
  [/\(COR\)/, "Core operating costs"],
  [/\(ROC\)/, "Cash generated"],
  [/^Cycle \/ liquidation/, "Cycle normalisation"],
  [/\(CAOCG\)/, "Cycle-adjusted"],
  [/^Robust-centre/, "Robust centre and trend"],
  [/^Maintenance capex/, "Maintenance capex reserve"],
  [/^Permitted/, "Permitted adjustments"],
  [/\(SBCI\)/, "Sustainable income"],
  [/\(UWI\)/, "Underwriting income"],
];

const friendly = (line: string) => FRIENDLY.find(([re]) => re.test(line))?.[1] ?? line.replace(/^Less: /, "");
const codeOf = (line: string) => /\((EOC|COR|ROC|CAOCG|SBCI|UWI)\)/.exec(line)?.[1];

const STAGE_COLOR: Record<string, string> = { TOTAL: "#94a1b6", SUBTOTAL: "#38bdf8", RESULT: "#34d399", POLICY: "#a78bfa" };
const SINK = "#fb7185";
const ADJUST = "#fbbf24";
const HELD = "#7c6fb0";

interface FlowNode {
  id: string;
  label: string;
  code?: string;
  value: number;
  x: number;
  y: number;
  h: number;
  color: string;
  kind: "stage" | "sink" | "source";
}

interface FlowLink {
  id: string;
  from: string;
  to: string;
  value: number;
  path: string;
  centre: string;
  thickness: number;
  x0: number;
  x1: number;
  c0: string;
  c1: string;
  main: boolean;
}

const W = 1000;
const NODE_W = 10;
const MAIN_H = 190;
const SLOT_GAP = 22;

function band(x0: number, y0: number, x1: number, y1: number, t: number): { path: string; centre: string } {
  const xm = (x0 + x1) / 2;
  return {
    path: `M${x0},${y0} C${xm},${y0} ${xm},${y1} ${x1},${y1} L${x1},${y1 + t} C${xm},${y1 + t} ${xm},${y0 + t} ${x0},${y0 + t} Z`,
    centre: `M${x0},${y0 + t / 2} C${xm},${y0 + t / 2} ${xm},${y1 + t / 2} ${x1},${y1 + t / 2}`,
  };
}

/** Bridge lines -> stages (gross, EOC, ROC, CAOCG, SBCI, UWI) joined by signed adjustments. */
function stagesOf(bridge: BridgeLine[]) {
  const stages: { line: string; value: number; kind: string }[] = [];
  const steps: { line: string; amount: number }[][] = [];
  let pending: { line: string; amount: number }[] = [];
  for (const b of bridge) {
    if (b.kind === "MEMO") continue;
    if (b.kind === "DEDUCTION" || b.kind === "ADJUSTMENT") {
      if (Math.abs(b.monthly_amount) >= 0.005) pending.push({ line: b.line, amount: b.monthly_amount });
      continue;
    }
    if (b.kind === "POLICY") {
      const prev = stages[stages.length - 1];
      if (prev) pending.push({ line: "Held back by policy", amount: b.monthly_amount - prev.value });
    }
    if (stages.length) steps.push(pending.filter((p) => Math.abs(p.amount) >= 0.005));
    pending = [];
    stages.push({ line: b.line, value: Math.max(0, b.monthly_amount), kind: b.kind });
  }
  return { stages, steps };
}

function layout(bridge: BridgeLine[]) {
  const { stages, steps } = stagesOf(bridge);
  if (stages.length < 2) return null;
  const k = MAIN_H / Math.max(...stages.map((s) => s.value), 1);
  const th = (v: number) => Math.abs(v) * k;
  const vis = (v: number) => Math.max(2, th(v));
  const colX = (i: number) => 8 + (i * (W - 210)) / (stages.length - 1);

  const sourceSpace = Math.max(0, ...steps.map((s) => s.filter((a) => a.amount > 0).reduce((n, a) => n + vis(a.amount) + SLOT_GAP, 0)));
  const top = 18 + sourceSpace;

  const nodes: FlowNode[] = stages.map((s, i) => ({
    id: `stage${i}`,
    label: friendly(s.line),
    code: codeOf(s.line),
    value: s.value,
    x: colX(i),
    y: top,
    h: vis(s.value),
    color: STAGE_COLOR[s.kind] ?? "#38bdf8",
    kind: "stage",
  }));
  const links: FlowLink[] = [];
  const link = (id: string, from: FlowNode, fromY: number, to: FlowNode, toY: number, value: number, main: boolean) => {
    const t = th(value);
    const x0 = from.x + NODE_W;
    const x1 = to.x;
    const { path, centre } = band(x0, fromY, x1, toY, Math.max(t, 1.2));
    links.push({ id, from: from.label, to: to.label, value, path, centre, thickness: t, x0, x1, c0: from.color, c1: to.color, main });
  };

  steps.forEach((adjustments, i) => {
    const a = nodes[i];
    const b = nodes[i + 1];
    const sinks = adjustments.filter((x) => x.amount < 0);
    const sources = adjustments.filter((x) => x.amount > 0);
    const carry = Math.max(0, a.value + sinks.reduce((n, x) => n + x.amount, 0));

    let srcY = top - 8;
    const sourceNodes = sources.map((s, j) => {
      srcY -= vis(s.amount) + (j ? SLOT_GAP : 6);
      const n: FlowNode = { id: `src${i}-${j}`, label: friendly(s.line), value: s.amount, x: a.x, y: srcY, h: vis(s.amount), color: ADJUST, kind: "source" };
      nodes.push(n);
      return n;
    });

    let sinkY = b.y + b.h + SLOT_GAP;
    const sinkNodes = sinks.map((s, j) => {
      const policy = s.line === "Held back by policy";
      const n: FlowNode = {
        id: `sink${i}-${j}`,
        label: friendly(s.line),
        code: codeOf(s.line),
        value: -s.amount,
        x: b.x,
        y: sinkY,
        h: vis(s.amount),
        color: policy ? HELD : /Cycle|Robust|Permitted/.test(s.line) ? ADJUST : SINK,
        kind: "sink",
      };
      sinkY += n.h + SLOT_GAP;
      nodes.push(n);
      return n;
    });

    let outY = a.y;
    let inY = b.y;
    sourceNodes.forEach((n, j) => {
      link(`s${i}-${j}`, n, n.y, b, inY, n.value, false);
      inY += th(n.value);
    });
    link(`m${i}`, a, outY, b, inY, carry, true);
    outY += th(carry);
    sinkNodes.forEach((n, j) => {
      link(`d${i}-${j}`, a, outY, n, n.y, n.value, false);
      outY += th(n.value);
    });
  });

  const height = Math.max(...nodes.map((n) => n.y + n.h)) + 26;
  return { nodes, links, height, gross: stages[0].value };
}

/** The economic bridge as an animated money-flow (Sankey) diagram. */
export default function MoneyFlow({ bridge }: { bridge: BridgeLine[] }) {
  const model = useMemo(() => layout(bridge), [bridge]);
  const [hover, setHover] = useState<string | null>(null);
  if (!model) return null;
  const active = model.links.find((l) => l.id === hover);

  return (
    <div>
      <div className="overflow-x-auto">
        <svg viewBox={`0 0 ${W} ${model.height}`} className="min-w-[760px]" role="img" aria-label="Money flow from gross credits to underwriting income">
          <defs>
            {model.links.map((l) => (
              <linearGradient key={l.id} id={`flow-${l.id}`} gradientUnits="userSpaceOnUse" x1={l.x0} x2={l.x1} y1={0} y2={0}>
                <stop offset="0%" stopColor={l.c0} />
                <stop offset="100%" stopColor={l.c1} />
              </linearGradient>
            ))}
          </defs>
          <g className="reveal-x">
            {model.links.map((l) => (
              <path
                key={l.id}
                d={l.path}
                fill={`url(#flow-${l.id})`}
                fillOpacity={hover ? (hover === l.id ? 0.55 : 0.08) : l.main ? 0.3 : 0.22}
                className="cursor-pointer transition-[fill-opacity] duration-200"
                onMouseEnter={() => setHover(l.id)}
                onMouseLeave={() => setHover(null)}
              />
            ))}
            {model.links
              .filter((l) => l.thickness >= 3)
              .map((l) => (
                <path
                  key={`dash-${l.id}`}
                  d={l.centre}
                  fill="none"
                  stroke="#fff"
                  strokeOpacity={hover && hover !== l.id ? 0.05 : 0.45}
                  strokeWidth={Math.min(3, Math.max(1.2, l.thickness * 0.04))}
                  strokeLinecap="round"
                  className="flow-dash pointer-events-none"
                  style={{ animationDuration: `${l.main ? 1.4 : 2.2}s` }}
                />
              ))}
          </g>
          {model.nodes.map((n, i) => (
            <rect
              key={n.id}
              x={n.x}
              y={n.y}
              width={NODE_W}
              height={n.h}
              rx={2.5}
              fill={n.color}
              className="pop"
              style={{ animationDelay: `${0.15 + i * 0.05}s`, transformBox: "fill-box", transformOrigin: "center" }}
            />
          ))}
          {model.nodes.map((n, i) => {
            const last = n.kind === "stage" && n.x > W - 260;
            return (
              <g key={n.id} className="pop" style={{ animationDelay: `${0.15 + i * 0.05}s`, transformBox: "fill-box", transformOrigin: "center" }}>
                <text
                  x={n.x + NODE_W + 6}
                  y={n.kind === "stage" ? n.y + Math.min(n.h / 2, 30) : n.y + n.h / 2}
                  dominantBaseline="middle"
                  className="fill-ink-100 text-[12px] font-medium"
                  stroke="#0b1019"
                  strokeWidth={3}
                  paintOrder="stroke"
                >
                  {n.label}
                  <tspan x={n.x + NODE_W + 6} dy={14} className={last ? "fill-ink-100 text-[13px] font-semibold" : "fill-ink-300 text-[11px] font-normal"}>
                    {n.code && <tspan className="fill-ink-400 font-mono">{`${n.code} · `}</tspan>}
                    {inr(n.value)}
                    {n.kind !== "stage" && model.gross > 0 && <tspan className="fill-ink-400">{`  ${pct(n.value / model.gross)}`}</tspan>}
                  </tspan>
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      <div className="mt-2 flex min-h-5 items-center gap-2 text-xs text-ink-300">
        {active ? (
          <>
            <span className="h-2 w-2 rounded-full" style={{ background: active.c1 }} />
            <span className="text-ink-100">{active.from}</span>→<span className="text-ink-100">{active.to}</span>
            <span className="font-mono text-ink-100 tabular">{inr(active.value, 2)}</span> / month
            <span className="text-ink-400">· {pct(active.value / model.gross)} of money in · {inrShort(active.value * 12)} a year</span>
          </>
        ) : (
          <span className="text-ink-400">Monthly equivalents. Band thickness is proportional to money; hover a flow for its amount.</span>
        )}
      </div>
    </div>
  );
}
