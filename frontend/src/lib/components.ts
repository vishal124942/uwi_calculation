import { inr, pct } from "./format";
import { stepHeadline } from "./headlines";
import { sectionsOf, type TraceState } from "./trace";
import type { Cell, ComponentKind, ComponentMeta, Meta, Table } from "./types";

export type Status = "done" | "running" | "pending" | "skipped";

/**
 * How a component shows a pipeline step it shares with another component: which part of the step view to render,
 * which of the step's transaction columns it owns (false = none), and which raw tables (RegExp filters the
 * `section` column of key/value tables). Unlisted (component, step) pairs show the whole step.
 */
export interface PartView {
  part?: string;
  columns?: RegExp | false;
  tables?: Record<string, RegExp | true>;
}

const PART_VIEWS: Record<string, Record<string, PartView>> = {
  M2: { step04_role_inference: { part: "model", columns: /^s04_(model|calibrated)_/, tables: {} } },
  M3: { step04_role_inference: { part: "rules", columns: /^s04_(top|second|rules_applied|probabilities)/, tables: {} } },
  LEDGER: {
    step06_aggregation_archetype_cash: {
      part: "ledger",
      tables: { step06_monthly_totals: true, step06_window_totals: true, step06_pass_through_summary: true },
    },
  },
  M5: { step06_aggregation_archetype_cash: { part: "archetype", columns: false, tables: { step06_archetype: true } } },
  M6: { step07_risk_signals: { part: "cycle", tables: { step07_risk_signals: /^s13_/, step07_cycle_lag_profile: true } } },
  SIGNALS: {
    step07_risk_signals: {
      part: "signals",
      tables: { step07_risk_signals: /^(?!s13_)/, step07_daily_balance: true, step07_financing_events: true },
    },
  },
  M8: { step09_uncertainty_and_policy: { part: "uncertainty", tables: { step09_uncertainty_and_policy: /^s22_/ } } },
  M9: { step09_uncertainty_and_policy: { part: "policy", tables: { step09_uncertainty_and_policy: /^s21_/ } } },
};

export function partView(componentId: string, step: string): PartView {
  return PART_VIEWS[componentId]?.[step] ?? {};
}

export const KIND_LABEL: Record<ComponentKind, string> = {
  model: "Section 24.1 model component",
  gate: "Supporting stage · gate",
  features: "Supporting stage · feature engine",
  output: "Supporting stage · output",
};

/** Short chip text: the M number for model components, the stage kind otherwise. */
export function componentCode(c: ComponentMeta): string {
  return c.kind === "model" ? c.id : { gate: "GATE", features: "INPUT", output: "AUDIT", model: c.id }[c.kind];
}

export function stepStatuses(meta: Meta | null, trace: TraceState): Record<string, Status> {
  const out: Record<string, Status> = {};
  let runningAssigned = false;
  for (const s of meta?.steps ?? []) {
    if (trace.steps[s.id]) out[s.id] = "done";
    else if (trace.status === "running" && !runningAssigned) {
      out[s.id] = "running";
      runningAssigned = true;
    } else out[s.id] = trace.status === "done" ? "skipped" : "pending";
  }
  return out;
}

export function componentStatuses(meta: Meta | null, trace: TraceState): Record<string, Status> {
  const steps = stepStatuses(meta, trace);
  const out: Record<string, Status> = {};
  for (const c of meta?.components ?? []) {
    const s = c.steps.map((id) => steps[id]);
    out[c.id] = s.every((x) => x === "done")
      ? "done"
      : s.some((x) => x === "running") || s.some((x) => x === "done")
        ? "running"
        : s.some((x) => x === "skipped")
          ? "skipped"
          : "pending";
  }
  return out;
}

/** Components whose modules run in the given pipeline step. */
export function componentsInStep(meta: Meta | null, step: string): ComponentMeta[] {
  return (meta?.components ?? []).filter((c) => c.steps.includes(step));
}

/** Engine time of the component's pipeline steps; components sharing a step share its time. */
export function componentTiming(meta: Meta | null, trace: TraceState, c: ComponentMeta) {
  const ms = c.steps.reduce((a, s) => a + (trace.steps[s]?.compute_ms ?? 0), 0);
  const sharedWith = [...new Set(c.steps.flatMap((s) => componentsInStep(meta, s).map((o) => o.id)))].filter((id) => id !== c.id);
  return { ms, sharedWith };
}

export function componentColumns(c: ComponentMeta, trace: TraceState): string[] {
  return c.steps.flatMap((step) => {
    const filter = partView(c.id, step).columns;
    const cols = trace.columnsByStep[step] ?? [];
    return filter === false ? [] : filter ? cols.filter((col) => filter.test(col)) : cols;
  });
}

export function componentTables(c: ComponentMeta, trace: TraceState): { name: string; table: Table }[] {
  return c.steps.flatMap((step) => {
    const tables = trace.steps[step]?.tables ?? {};
    const filter = partView(c.id, step).tables;
    return Object.entries(tables).flatMap(([name, table]) => {
      if (!filter) return [{ name, table }];
      const rule = filter[name];
      if (!rule) return [];
      if (rule === true) return [{ name, table }];
      return [{ name, table: { ...table, rows: table.rows.filter((r) => rule.test(String(r[0]))) } }];
    });
  });
}

/** One-line summary of what the component produced in this run. */
export function componentHeadline(c: ComponentMeta, trace: TraceState): string {
  const step = (id: string) => trace.steps[id];
  const tables = (id: string) => step(id)?.tables ?? {};
  const kv = (id: string, name: string) => sectionsOf(tables(id)[name]);
  const col = (id: string, name: string): Cell[] => {
    const d = step(id)?.transactions;
    const i = d ? d.columns.indexOf(name) : -1;
    return d && i >= 0 ? d.rows.map((r) => r[i]) : [];
  };
  const headlineOf = (id: string) => (step(id) ? stepHeadline(step(id)) : "");

  switch (c.id) {
    case "M2": {
      if (!step("step04_role_inference")) return headlineOf("step03_transaction_evidence");
      const p = col("step04_role_inference", "s04_calibrated_top_p") as number[];
      const confident = p.filter((x) => x >= 0.9).length;
      return `${headlineOf("step03_transaction_evidence")} · calibrated role distribution for ${p.length.toLocaleString("en-IN")} transactions, ${pct(confident / (p.length || 1))} with top role ≥ 90%`;
    }
    case "M3": {
      const rules = col("step04_role_inference", "s04_rules_applied").filter((r) => Array.isArray(r) && r.length).length;
      const model = col("step04_role_inference", "s04_model_top_role");
      const final = col("step04_role_inference", "s04_top_role");
      const changed = model.filter((r, i) => r !== final[i]).length;
      return `${rules.toLocaleString("en-IN")} transactions adjusted by versioned rules · ${changed} top roles overridden`;
    }
    case "M5": {
      const a = kv("step06_aggregation_archetype_cash", "step06_archetype");
      const top = Object.entries((a.probability ?? {}) as Record<string, number>).sort((x, y) => y[1] - x[1])[0];
      return `Selected archetype ${a.selected?.archetype ?? "—"}${top ? ` · most likely ${top[0]} at ${pct(top[1])}` : ""}`;
    }
    case "M6": {
      const s = kv("step07_risk_signals", "step07_risk_signals").s13_cycle ?? {};
      return `Cycle ${s.status ?? "—"} · build normalisation ${inr(s.build_normalisation_amount)} · liquidation normalisation ${inr(s.liquidation_normalisation_amount)}`;
    }
    case "SIGNALS": {
      const s = kv("step07_risk_signals", "step07_risk_signals");
      return `Coverage risk ${s.s20_coverage?.risk ?? "—"} · trend ${s.s18_trend?.regime ?? "—"} · anomaly review ${s.s19_anomaly?.review_required ? "required" : "not required"} · owner draw ${inr(s.s16_owner?.owner_draw_monthly)} / month`;
    }
    case "M8": {
      const u = kv("step09_uncertainty_and_policy", "step09_uncertainty_and_policy").s22_uncertainty ?? {};
      return `Confidence ${pct(u.confidence)} · interval ${inr(u.lower)} – ${inr(u.upper)} · ${u.interval_method ?? ""}`;
    }
    case "M9": {
      const d = kv("step09_uncertainty_and_policy", "step09_uncertainty_and_policy").s21_policy_decision ?? {};
      return `UWI ${inr(d.underwriting_income_monthly)} / month · ${d.status ?? ""} · basis ${d.basis ?? ""}`;
    }
    default:
      return c.steps.map(headlineOf).filter(Boolean).join(" · ");
  }
}