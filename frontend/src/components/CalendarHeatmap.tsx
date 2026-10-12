"use client";

import { useMemo, useState } from "react";
import { inr, inrShort } from "@/lib/format";
import type { DayFlow } from "@/lib/insights";
import { quantile } from "@/lib/whatif";
import { cx } from "./ui";

type Mode = "in" | "out" | "net";

const CELL = 13;
const GAP = 3;
const STEP = CELL + GAP;
const LEFT = 30;
const TOP = 20;
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const weekday = (date: string) => (new Date(`${date}T00:00:00Z`).getUTCDay() + 6) % 7;
const valueOf = (d: DayFlow, mode: Mode) => (mode === "in" ? d.credits : mode === "out" ? d.debits : d.credits - d.debits);

function colour(v: number, scale: number, mode: Mode): string {
  if (!v) return "rgba(255,255,255,0.04)";
  const t = Math.min(1, Math.sqrt(Math.abs(v) / (scale || 1)));
  const a = 0.12 + 0.88 * t;
  const positive = mode === "in" || (mode === "net" && v > 0);
  return positive ? `rgba(52,211,153,${a})` : `rgba(251,113,133,${a})`;
}

/** GitHub-style calendar of daily money in / out, with the average weekday rhythm alongside. */
export default function CalendarHeatmap({ days }: { days: DayFlow[] }) {
  const [mode, setMode] = useState<Mode>("in");
  const [hover, setHover] = useState<DayFlow | null>(null);

  const { cells, weeks, monthLabels, scale, rhythm, best } = useMemo(() => {
    const offset = days.length ? weekday(days[0].date) : 0;
    const cells = days.map((d, i) => ({ d, col: Math.floor((i + offset) / 7), row: (i + offset) % 7 }));
    const values = days.map((d) => Math.abs(valueOf(d, mode))).filter(Boolean);
    const scale = quantile(values, 0.95) ?? 1;
    const monthLabels: { col: number; label: string }[] = [];
    for (const c of cells) {
      if (c.d.date.endsWith("-01") || c === cells[0]) {
        const m = Number(c.d.date.slice(5, 7)) - 1;
        if (!monthLabels.length || monthLabels[monthLabels.length - 1].col < c.col - 2) monthLabels.push({ col: c.col + (c.row ? 1 : 0), label: MONTHS[m] });
      }
    }
    const sums = Array.from({ length: 7 }, () => ({ credits: 0, debits: 0, n: 0 }));
    for (const c of cells) {
      sums[c.row].credits += c.d.credits;
      sums[c.row].debits += c.d.debits;
      sums[c.row].n += 1;
    }
    const rhythm = sums.map((s, i) => ({ day: WEEKDAYS[i], credits: s.n ? s.credits / s.n : 0, debits: s.n ? s.debits / s.n : 0 }));
    const best = days.reduce<DayFlow | null>((b, d) => (!b || valueOf(d, mode) > valueOf(b, mode) ? d : b), null);
    return { cells, weeks: (cells[cells.length - 1]?.col ?? 0) + 1, monthLabels, scale, rhythm, best };
  }, [days, mode]);

  const rhythmMax = Math.max(...rhythm.map((r) => Math.max(r.credits, r.debits)), 1);
  const busiest = rhythm.reduce((a, b) => (b.credits > a.credits ? b : a));
  const heaviest = rhythm.reduce((a, b) => (b.debits > a.debits ? b : a));
  const width = LEFT + weeks * STEP;
  const shown = hover ?? best;

  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_15rem]">
      <div className="min-w-0">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div className="inline-flex rounded-lg border border-white/[0.07] bg-ink-950/50 p-0.5 text-xs">
            {(
              [
                ["in", "Money in"],
                ["out", "Money out"],
                ["net", "Net"],
              ] as [Mode, string][]
            ).map(([m, label]) => (
              <button key={m} onClick={() => setMode(m)} className={cx("rounded-md px-3 py-1 transition", mode === m ? "bg-white/10 text-ink-100" : "text-ink-400 hover:text-ink-100")}>
                {label}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1.5 text-[11px] text-ink-400">
            less
            {[0.05, 0.2, 0.45, 0.75, 1].map((t) => (
              <span key={t} className="h-2.5 w-2.5 rounded-[3px]" style={{ background: colour(t * t * scale, scale, mode === "out" ? "out" : "in") }} />
            ))}
            more
          </div>
        </div>
        <div className="overflow-x-auto">
          <svg viewBox={`0 0 ${width} ${TOP + 7 * STEP}`} className="w-full min-w-[640px]" onMouseLeave={() => setHover(null)}>
            {monthLabels.map((m) => (
              <text key={`${m.col}-${m.label}`} x={LEFT + m.col * STEP} y={11} className="fill-ink-400 text-[10px]">
                {m.label}
              </text>
            ))}
            {[0, 2, 4].map((r) => (
              <text key={r} x={0} y={TOP + r * STEP + CELL - 2} className="fill-ink-500 text-[9.5px]">
                {WEEKDAYS[r]}
              </text>
            ))}
            {cells.map(({ d, col, row }) => (
              <rect
                key={d.date}
                x={LEFT + col * STEP}
                y={TOP + row * STEP}
                width={CELL}
                height={CELL}
                rx={3}
                fill={colour(valueOf(d, mode), scale, mode)}
                stroke={hover?.date === d.date ? "#e6eaf1" : "transparent"}
                strokeWidth={1.2}
                className="transition-[fill] duration-300"
                onMouseEnter={() => setHover(d)}
              />
            ))}
          </svg>
        </div>
        <div className="mt-2 min-h-5 text-xs text-ink-300">
          {shown && (
            <>
              <span className="text-ink-400">{hover ? "" : mode === "out" ? "Biggest outflow day · " : mode === "net" ? "Best net day · " : "Biggest inflow day · "}</span>
              <span className="font-medium text-ink-100">
                {new Date(`${shown.date}T00:00:00Z`).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short", year: "numeric", timeZone: "UTC" })}
              </span>
              <span className="ml-3 text-emerald-300">in {inr(shown.credits)}</span>
              <span className="ml-3 text-rose-300">out {inr(shown.debits)}</span>
              <span className="ml-3 text-ink-200">net {inr(shown.credits - shown.debits)}</span>
              <span className="ml-3 text-ink-400">{shown.count} transactions</span>
            </>
          )}
        </div>
      </div>
      <div>
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-ink-400">Weekday rhythm (average per day)</div>
        <div className="space-y-2">
          {rhythm.map((r) => (
            <div key={r.day} className="grid grid-cols-[2rem_1fr] items-center gap-2 text-[11px]">
              <span className="text-ink-400">{r.day}</span>
              <div className="space-y-0.5">
                <div className="h-1.5 rounded-full bg-emerald-400/70 transition-all duration-500" style={{ width: `${(r.credits / rhythmMax) * 100}%` }} title={`in ${inr(r.credits)}`} />
                <div className="h-1.5 rounded-full bg-rose-400/60 transition-all duration-500" style={{ width: `${(r.debits / rhythmMax) * 100}%` }} title={`out ${inr(r.debits)}`} />
              </div>
            </div>
          ))}
        </div>
        <div className="mt-3 text-[11px] leading-relaxed text-ink-400">
          Busiest collection day: <span className="text-ink-200">{busiest.day}</span> ({inrShort(busiest.credits)} on average). Heaviest payout day:{" "}
          <span className="text-ink-200">{heaviest.day}</span> ({inrShort(heaviest.debits)}).
        </div>
      </div>
    </div>
  );
}
