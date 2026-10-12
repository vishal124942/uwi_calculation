"use client";

import { useMemo, useState } from "react";
import { inr, inrShort, pct } from "@/lib/format";
import type { Counterparty } from "@/lib/insights";
import { roleColor, roleLabel } from "@/lib/roles";

const W = 1000;
const H = 540;
const CX = W / 2;
const CY = H / 2;
const RX = 330;
const RY = 220;
const TOP_N = 10;

interface Placed {
  c: Counterparty;
  side: "in" | "out";
  amount: number;
  x: number;
  y: number;
  r: number;
  width: number;
  path: string;
}

function place(list: Counterparty[], side: "in" | "out", max: number): Placed[] {
  const n = list.length;
  const [from, to] = side === "in" ? [125, 235] : [-55, 55];
  return list.map((c, i) => {
    const deg = n === 1 ? (from + to) / 2 : side === "in" ? from + ((to - from) * i) / (n - 1) : to - ((to - from) * i) / (n - 1);
    const a = (deg * Math.PI) / 180;
    const x = CX + RX * Math.cos(a);
    const y = CY - RY * Math.sin(a);
    const amount = side === "in" ? c.credit : c.debit;
    const ctrlX = CX + (x - CX) * 0.4;
    const path = side === "in" ? `M${x},${y} Q${ctrlX},${y} ${CX},${CY}` : `M${CX},${CY} Q${ctrlX},${y} ${x},${y}`;
    return { c, side, amount, x, y, r: 4 + 15 * Math.sqrt(amount / max), width: 1 + 13 * (amount / max), path };
  });
}

/** The business at the centre, its largest payers (left) and payees (right); edge width is money, colour is role. */
export default function CounterpartyNetwork({
  parties,
  roles,
  onOpenTxn,
}: {
  parties: Counterparty[];
  roles?: Record<string, string>;
  onOpenTxn: (id: string) => void;
}) {
  const [hover, setHover] = useState<string | null>(null);
  const { placed, totalIn, totalOut, topInShare, topOutShare } = useMemo(() => {
    const payers = parties.filter((p) => p.credit > 0).sort((a, b) => b.credit - a.credit);
    const payees = parties.filter((p) => p.debit > 0).sort((a, b) => b.debit - a.debit);
    const totalIn = payers.reduce((n, p) => n + p.credit, 0);
    const totalOut = payees.reduce((n, p) => n + p.debit, 0);
    const ins = payers.slice(0, TOP_N);
    const outs = payees.slice(0, TOP_N);
    const max = Math.max(...ins.map((p) => p.credit), ...outs.map((p) => p.debit), 1);
    return {
      placed: [...place(ins, "in", max), ...place(outs, "out", max)],
      totalIn,
      totalOut,
      topInShare: totalIn ? ins.reduce((n, p) => n + p.credit, 0) / totalIn : 0,
      topOutShare: totalOut ? outs.reduce((n, p) => n + p.debit, 0) / totalOut : 0,
    };
  }, [parties]);

  const key = (p: Placed) => `${p.side}:${p.c.id}`;
  const active = placed.find((p) => key(p) === hover);

  return (
    <div>
      <div className="overflow-x-auto">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full min-w-[720px]" onMouseLeave={() => setHover(null)}>
          <defs>
            <radialGradient id="net-core" cx="50%" cy="40%" r="70%">
              <stop offset="0%" stopColor="#7dd3fc" />
              <stop offset="100%" stopColor="#7c3aed" />
            </radialGradient>
          </defs>
          {placed.map((p) => {
            const dim = hover && hover !== key(p);
            return (
              <g key={key(p)}>
                <path d={p.path} fill="none" stroke={roleColor(p.c.role)} strokeOpacity={dim ? 0.08 : 0.45} strokeWidth={p.width} strokeLinecap="round" className="transition-[stroke-opacity] duration-200" />
                <path
                  d={p.path}
                  fill="none"
                  stroke="#fff"
                  strokeOpacity={dim ? 0 : 0.5}
                  strokeWidth={Math.max(1, p.width * 0.18)}
                  strokeLinecap="round"
                  className="flow-dash pointer-events-none"
                  style={{ animationDuration: `${2.6 - Math.min(1.4, p.width / 10)}s` }}
                />
              </g>
            );
          })}
          {placed.map((p, i) => {
            const dim = hover && hover !== key(p);
            const left = p.side === "in";
            return (
              <g
                key={`n-${key(p)}`}
                className="pop cursor-pointer"
                style={{ animationDelay: `${0.1 + i * 0.03}s`, transformBox: "fill-box", transformOrigin: "center", opacity: dim ? 0.35 : 1, transition: "opacity 0.2s" }}
                onMouseEnter={() => setHover(key(p))}
                onClick={() => onOpenTxn(p.c.largestTxn)}
              >
                <circle cx={p.x} cy={p.y} r={p.r + 6} fill="transparent" />
                <circle cx={p.x} cy={p.y} r={p.r} fill={roleColor(p.c.role)} fillOpacity={0.85} stroke="#0b1019" strokeWidth={2} />
                <text x={p.x + (left ? -(p.r + 7) : p.r + 7)} y={p.y - 2} textAnchor={left ? "end" : "start"} className="fill-ink-100 text-[12px] font-medium" stroke="#0b1019" strokeWidth={3} paintOrder="stroke">
                  {p.c.name.length > 26 ? `${p.c.name.slice(0, 25)}…` : p.c.name}
                </text>
                <text x={p.x + (left ? -(p.r + 7) : p.r + 7)} y={p.y + 12} textAnchor={left ? "end" : "start"} className="fill-ink-400 text-[10.5px]" stroke="#0b1019" strokeWidth={3} paintOrder="stroke">
                  {inrShort(p.amount)} · {p.c.count} txns
                </text>
              </g>
            );
          })}
          <g className="pop" style={{ transformBox: "fill-box", transformOrigin: "center" }}>
            <circle cx={CX} cy={CY} r={46} fill="url(#net-core)" fillOpacity={0.9} />
            <circle cx={CX} cy={CY} r={50} fill="none" stroke="#a78bfa" strokeWidth={1.5}>
              <animate attributeName="r" values="48;64;48" dur="3.2s" repeatCount="indefinite" />
              <animate attributeName="stroke-opacity" values="0.5;0;0.5" dur="3.2s" repeatCount="indefinite" />
            </circle>
            <text x={CX} y={CY - 12} textAnchor="middle" className="fill-white text-[12px] font-semibold">This business</text>
            <text x={CX} y={CY + 4} textAnchor="middle" className="fill-white/80 text-[10.5px]">
              {inrShort(totalIn)} in · {inrShort(totalOut)} out
            </text>
            <text x={CX} y={CY + 18} textAnchor="middle" className="fill-white/65 text-[10px]">
              net {totalIn >= totalOut ? "+" : "−"}
              {inr(Math.abs(totalIn - totalOut))}
            </text>
          </g>
          <text x={40} y={24} className="fill-emerald-300/80 text-[11px] font-semibold uppercase tracking-wider">Who pays in</text>
          <text x={W - 40} y={24} textAnchor="end" className="fill-rose-300/80 text-[11px] font-semibold uppercase tracking-wider">Who gets paid</text>
        </svg>
      </div>
      <div className="mt-2 min-h-5 text-xs text-ink-300">
        {active ? (
          <>
            <span className="mr-2 inline-block h-2 w-2 rounded-full" style={{ background: roleColor(active.c.role) }} />
            <span className="font-medium text-ink-100">{active.c.name}</span>
            <span className="ml-2 text-ink-400">{active.c.role ? `${active.c.role} ${roleLabel(roles, active.c.role)}` : "no role"}</span>
            <span className="ml-3 text-emerald-300">in {inr(active.c.credit)}</span>
            <span className="ml-3 text-rose-300">out {inr(active.c.debit)}</span>
            <span className="ml-3 text-ink-400">
              {active.c.count} transactions · active {active.c.months} months · click to open its largest transaction
            </span>
          </>
        ) : (
          <span className="text-ink-400">
            Top {TOP_N} payers bring {pct(topInShare)} of money in; top {TOP_N} payees take {pct(topOutShare)} of money out. {parties.length.toLocaleString("en-IN")}{" "}
            counterparties in total (M2 entity resolution). Hover a counterparty for detail.
          </span>
        )}
      </div>
    </div>
  );
}
