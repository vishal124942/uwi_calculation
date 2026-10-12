"use client";

import { BookOpen, Check, CircleDashed, Gauge, Loader2, PieChart, Plus, Rows3, X } from "lucide-react";
import { componentStatuses, componentTiming, type Status } from "@/lib/components";
import { ms } from "@/lib/format";
import type { TraceState } from "@/lib/trace";
import type { Meta } from "@/lib/types";
import { ComponentChip } from "./ComponentView";
import { cx } from "./ui";

/** "start" | "overview" | "story" | "roles" | "transactions" or a component id (M1 … M9, DQ, LEDGER, SIGNALS, AUDIT). */
export type View = string;

export function StatusDot({ status }: { status: Status }) {
  if (status === "done")
    return (
      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-400/15 text-emerald-300 ring-1 ring-emerald-400/30">
        <Check className="h-3 w-3" strokeWidth={3} />
      </span>
    );
  if (status === "running")
    return (
      <span className="pulse-ring flex h-5 w-5 items-center justify-center rounded-full bg-sky-400/15 text-sky-300 ring-1 ring-sky-400/40">
        <Loader2 className="h-3 w-3 animate-spin" />
      </span>
    );
  if (status === "skipped")
    return (
      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-rose-400/10 text-rose-300 ring-1 ring-rose-400/25">
        <X className="h-3 w-3" />
      </span>
    );
  return (
    <span className="flex h-5 w-5 items-center justify-center text-ink-500">
      <CircleDashed className="h-4 w-4" />
    </span>
  );
}

function NavButton({ active, onClick, disabled, children }: { active: boolean; onClick: () => void; disabled?: boolean; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={cx(
        "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] transition",
        active ? "bg-white/[0.08] text-ink-100" : "text-ink-300 hover:bg-white/[0.04] hover:text-ink-100",
        disabled && "pointer-events-none opacity-40",
      )}
    >
      {children}
    </button>
  );
}

export default function Sidebar({
  meta,
  trace,
  view,
  onView,
}: {
  meta: Meta | null;
  trace: TraceState;
  view: View;
  onView: (v: View) => void;
}) {
  const statuses = componentStatuses(meta, trace);
  const hasRun = trace.status !== "idle";

  return (
    <aside className="sticky top-0 hidden h-screen w-72 shrink-0 flex-col border-r border-white/[0.06] bg-ink-900/60 backdrop-blur lg:flex">
      <div className="px-5 pb-4 pt-5">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-sky-400 to-violet-500 text-sm font-bold text-ink-950">
            ₹
          </div>
          <div>
            <div className="text-sm font-semibold tracking-tight">UWI Pipeline Explorer</div>
            <div className="text-[11px] text-ink-400">Income reconstruction engine {meta ? `v${meta.version}` : ""}</div>
          </div>
        </div>
        <button
          onClick={() => onView("start")}
          className="mt-4 flex w-full items-center justify-center gap-1.5 rounded-lg border border-white/10 bg-white/[0.04] py-2 text-xs font-medium text-ink-100 transition hover:bg-white/[0.08]"
        >
          <Plus className="h-3.5 w-3.5" /> New analysis
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 pb-6">
        <div className="space-y-0.5">
          <NavButton active={view === "overview"} onClick={() => onView("overview")} disabled={!hasRun}>
            <Gauge className="h-4 w-4" /> Result overview
          </NavButton>
          <NavButton active={view === "story"} onClick={() => onView("story")} disabled={!trace.result?.underwriting}>
            <BookOpen className="h-4 w-4" /> Business story
          </NavButton>
          <NavButton active={view === "roles"} onClick={() => onView("roles")} disabled={!trace.steps.step04_role_inference}>
            <PieChart className="h-4 w-4" /> Role distribution
          </NavButton>
          <NavButton active={view === "transactions"} onClick={() => onView("transactions")} disabled={!trace.order.length}>
            <Rows3 className="h-4 w-4" /> Transaction journey
            {trace.order.length > 0 && <span className="ml-auto text-[11px] text-ink-400 tabular">{trace.order.length.toLocaleString("en-IN")}</span>}
          </NavButton>
        </div>

        <div className="mb-1 mt-6 px-2.5 text-[11px] font-semibold uppercase tracking-wider text-ink-400">Components · spec §24.1</div>
        <div className="mb-2 px-2.5 text-[10.5px] leading-snug text-ink-500">M1–M9 in execution order, with the supporting stages between them</div>
        <ol className="relative space-y-0.5">
          {(meta?.components ?? []).map((c, i, all) => {
            const status = statuses[c.id];
            const timing = componentTiming(meta, trace, c);
            return (
              <li key={c.id} className="relative">
                {i < all.length - 1 && (
                  <span className={cx("absolute left-[1.3rem] top-8 h-[calc(100%-1rem)] w-px", status === "done" ? "bg-emerald-400/30" : "bg-white/[0.06]")} />
                )}
                <NavButton active={view === c.id} onClick={() => onView(c.id)} disabled={status !== "done"}>
                  <StatusDot status={status} />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-start gap-1.5">
                      <ComponentChip c={c} className="mt-px shrink-0" />
                      <span className={cx("leading-snug", c.kind !== "model" && "text-ink-300")}>{c.name}</span>
                    </span>
                    <span className="block text-[10.5px] text-ink-400">{c.sections}</span>
                  </span>
                  {status === "done" && (
                    <span
                      className="shrink-0 text-[10.5px] text-ink-400 tabular"
                      title={timing.sharedWith.length ? `Pipeline step time, shared with ${timing.sharedWith.join(", ")}` : "Pipeline step time"}
                    >
                      {ms(timing.ms)}
                      {timing.sharedWith.length > 0 && "*"}
                    </span>
                  )}
                </NavButton>
              </li>
            );
          })}
        </ol>
        <div className="mt-3 px-2.5 text-[10px] leading-snug text-ink-500">* time of a pipeline step shared with another component</div>
      </nav>
    </aside>
  );
}
