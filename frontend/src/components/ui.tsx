"use client";

import type { ReactNode } from "react";
import { cellText, featureName } from "@/lib/format";
import type { Cell } from "@/lib/types";

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <section className={cx("spotlight relative rounded-2xl border border-white/[0.07] bg-ink-900/70 backdrop-blur-sm transition-colors", className)}>
      {children}
    </section>
  );
}

export function CardHeader({ title, subtitle, right }: { title: ReactNode; subtitle?: ReactNode; right?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-white/[0.06] px-5 py-4">
      <div>
        <h3 className="text-sm font-semibold text-ink-100">{title}</h3>
        {subtitle && <p className="mt-0.5 text-xs leading-relaxed text-ink-300">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}

export function CardBody({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx("p-5", className)}>{children}</div>;
}

const TONES = {
  neutral: "bg-white/[0.06] text-ink-200 ring-white/10",
  good: "bg-emerald-400/10 text-emerald-300 ring-emerald-400/25",
  bad: "bg-rose-400/10 text-rose-300 ring-rose-400/25",
  warn: "bg-amber-400/10 text-amber-300 ring-amber-400/25",
  info: "bg-sky-400/10 text-sky-300 ring-sky-400/25",
  policy: "bg-violet-400/10 text-violet-300 ring-violet-400/25",
} as const;

export type Tone = keyof typeof TONES;

export function Badge({ children, tone = "neutral", className }: { children: ReactNode; tone?: Tone; className?: string }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset whitespace-nowrap",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function statusTone(status: string | undefined): Tone {
  if (!status) return "neutral";
  if (status === "SUCCESS") return "good";
  if (status.startsWith("REFER")) return "warn";
  return "bad";
}

export function riskTone(level: string | undefined): Tone {
  if (level === "LOW") return "good";
  if (level === "MEDIUM") return "warn";
  if (level === "HIGH" || level === "INDETERMINATE") return "bad";
  return "neutral";
}

export function Stat({
  label,
  value,
  hint,
  tone,
  className,
}: {
  label: ReactNode;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "income" | "deduct" | "subtotal" | "policy" | "adjust";
  className?: string;
}) {
  const color = tone
    ? { income: "text-income", deduct: "text-deduct", subtotal: "text-subtotal", policy: "text-policy", adjust: "text-adjust" }[tone]
    : "text-ink-100";
  return (
    <div className={cx("rounded-xl border border-white/[0.06] bg-ink-850/60 px-4 py-3", className)}>
      <div className="text-[11px] font-medium uppercase tracking-wider text-ink-400">{label}</div>
      <div className={cx("mt-1 text-xl font-semibold tabular", color)}>{value}</div>
      {hint && <div className="mt-0.5 text-xs text-ink-300">{hint}</div>}
    </div>
  );
}

export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
}: {
  tabs: { id: T; label: ReactNode; count?: number }[];
  value: T;
  onChange: (id: T) => void;
}) {
  return (
    <div className="inline-flex rounded-xl border border-white/[0.07] bg-ink-900/80 p-1">
      {tabs.map((t) => (
        <button
          key={t.id}
          onClick={() => onChange(t.id)}
          className={cx(
            "rounded-lg px-3.5 py-1.5 text-xs font-medium transition",
            value === t.id ? "bg-white/10 text-ink-100 shadow-sm" : "text-ink-300 hover:text-ink-100",
          )}
        >
          {t.label}
          {t.count !== undefined && <span className="ml-1.5 text-ink-400 tabular">{t.count.toLocaleString("en-IN")}</span>}
        </button>
      ))}
    </div>
  );
}

/** Feature/key-value grid; feature codes (BAL01_, WC06_, ...) are split into a code chip and a readable label. */
export function KeyValueGrid({
  data,
  format,
  columns = 2,
}: {
  data: Record<string, Cell>;
  format?: (key: string, value: Cell) => ReactNode;
  columns?: 1 | 2 | 3;
}) {
  const entries = Object.entries(data);
  if (!entries.length) return <Empty>No values</Empty>;
  return (
    <dl className={cx("grid gap-x-6", columns === 1 ? "grid-cols-1" : columns === 2 ? "md:grid-cols-2" : "md:grid-cols-3")}>
      {entries.map(([k, v]) => {
        const { code, label } = featureName(k);
        return (
          <div key={k} className="flex items-baseline justify-between gap-3 border-b border-white/[0.04] py-1.5">
            <dt className="flex min-w-0 items-baseline gap-2 text-xs text-ink-300">
              {code && <span className="font-mono text-[10px] text-ink-400">{code}</span>}
              <span className="truncate" title={k}>{label}</span>
            </dt>
            <dd className="shrink-0 text-right text-xs font-medium text-ink-100 tabular">
              {format ? format(k, v) : cellText(v)}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-xl border border-dashed border-white/10 px-4 py-6 text-center text-xs text-ink-400">{children}</div>;
}

/** One line of a worked calculation: operator, label, value. */
export function CalcLine({
  op,
  label,
  value,
  note,
  emphasis,
}: {
  op?: string;
  label: ReactNode;
  value: ReactNode;
  note?: ReactNode;
  emphasis?: boolean;
}) {
  return (
    <div className={cx("grid grid-cols-[1.5rem_1fr_auto] items-baseline gap-2 py-1.5", emphasis && "border-t border-white/10 pt-2.5")}>
      <span className="text-center font-mono text-sm text-ink-400">{op}</span>
      <span className={cx("text-sm", emphasis ? "font-semibold text-ink-100" : "text-ink-200")}>
        {label}
        {note && <span className="ml-2 text-xs text-ink-400">{note}</span>}
      </span>
      <span className={cx("text-right font-mono text-sm tabular", emphasis ? "font-semibold text-ink-100" : "text-ink-100")}>{value}</span>
    </div>
  );
}

export function Formula({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-sky-400/15 bg-sky-400/[0.04] px-4 py-3 font-mono text-[13px] leading-relaxed text-sky-100">
      {children}
    </div>
  );
}

export function Note({ children }: { children: ReactNode }) {
  return <p className="text-xs leading-relaxed text-ink-300">{children}</p>;
}

/** Horizontal probability bar list. */
export function ProbBars({
  probs,
  labels,
  colorOf,
  limit = 6,
}: {
  probs: Record<string, number>;
  labels?: Record<string, string>;
  colorOf: (code: string) => string;
  limit?: number;
}) {
  const entries = Object.entries(probs).sort((a, b) => b[1] - a[1]).slice(0, limit);
  return (
    <div className="space-y-1.5">
      {entries.map(([code, p]) => (
        <div key={code} className="grid grid-cols-[minmax(0,12rem)_minmax(0,1fr)_3.5rem] items-center gap-3">
          <div className="truncate text-[11px]" title={labels?.[code]}>
            <span className="font-mono font-semibold" style={{ color: colorOf(code) }}>{code}</span>
            <span className="ml-1.5 text-ink-300">{labels?.[code]}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-white/[0.05]">
            <div className="h-full rounded-full transition-all duration-500" style={{ width: `${Math.max(p * 100, 0.5)}%`, background: colorOf(code) }} />
          </div>
          <span className="text-right font-mono text-xs text-ink-200 tabular">{(p * 100).toFixed(1)}%</span>
        </div>
      ))}
    </div>
  );
}

export function SectionHeading({ children, hint }: { children: ReactNode; hint?: ReactNode }) {
  return (
    <div className="mb-3 mt-1">
      <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-300">{children}</h4>
      {hint && <p className="mt-1 text-xs text-ink-400">{hint}</p>}
    </div>
  );
}
