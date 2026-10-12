import { smartNumber } from "./format";
import type { Cell, Row } from "./types";

export type ColumnKind = "number" | "date" | "boolean" | "text";

export type Op = "eq" | "ne" | "gt" | "ge" | "lt" | "le" | "between" | "contains" | "not_contains" | "begins" | "ends" | "blank" | "not_blank";

export interface Condition {
  op: Op;
  a: string;
  b: string;
}

/** `values` lists the allowed value keys (null = every value); `condition` is the Excel-style custom filter. */
export interface ColumnFilter {
  values: string[] | null;
  condition: Condition | null;
}

export type Filters = Record<string, ColumnFilter>;

export const BLANK = "(Blanks)";

export const OPS: Record<ColumnKind, { op: Op; label: string }[]> = {
  number: [
    { op: "eq", label: "Equals" },
    { op: "ne", label: "Does not equal" },
    { op: "gt", label: "Greater than" },
    { op: "ge", label: "Greater than or equal to" },
    { op: "lt", label: "Less than" },
    { op: "le", label: "Less than or equal to" },
    { op: "between", label: "Between" },
    { op: "blank", label: "Is blank" },
    { op: "not_blank", label: "Is not blank" },
  ],
  date: [
    { op: "eq", label: "Equals" },
    { op: "lt", label: "Before" },
    { op: "le", label: "On or before" },
    { op: "gt", label: "After" },
    { op: "ge", label: "On or after" },
    { op: "between", label: "Between" },
    { op: "blank", label: "Is blank" },
    { op: "not_blank", label: "Is not blank" },
  ],
  text: [
    { op: "contains", label: "Contains" },
    { op: "not_contains", label: "Does not contain" },
    { op: "eq", label: "Equals" },
    { op: "ne", label: "Does not equal" },
    { op: "begins", label: "Begins with" },
    { op: "ends", label: "Ends with" },
    { op: "blank", label: "Is blank" },
    { op: "not_blank", label: "Is not blank" },
  ],
  boolean: [],
};

export function valueKey(v: Cell | undefined): string {
  if (v === null || v === undefined || v === "" || (Array.isArray(v) && !v.length)) return BLANK;
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

export function valueLabel(key: string, kind: ColumnKind): string {
  if (key === BLANK) return BLANK;
  if (kind === "number") return smartNumber(Number(key));
  if (kind === "boolean") return key === "true" ? "yes" : "no";
  return key;
}

const DATE = /^\d{4}-\d{2}-\d{2}([T ]|$)/;

export function columnKinds(rows: Row[], columns: string[]): Record<string, ColumnKind> {
  const kinds: Record<string, ColumnKind> = {};
  for (const col of columns) {
    let kind: ColumnKind | null = null;
    for (const r of rows) {
      const v = r[col];
      if (valueKey(v) === BLANK) continue;
      const k: ColumnKind =
        typeof v === "number" ? "number" : typeof v === "boolean" ? "boolean" : typeof v === "string" && DATE.test(v) ? "date" : "text";
      if (kind === null) kind = k;
      else if (kind !== k) {
        kind = "text";
        break;
      }
      if (kind === "text") break;
    }
    kinds[col] = kind ?? "text";
  }
  return kinds;
}

export function needsValue(op: Op): boolean {
  return op !== "blank" && op !== "not_blank";
}

/** A condition with an empty operand is incomplete and filters nothing. */
export function isComplete(c: Condition): boolean {
  if (!needsValue(c.op)) return true;
  if (c.a.trim() === "") return false;
  return c.op !== "between" || c.b.trim() !== "";
}

function matches(v: Cell | undefined, kind: ColumnKind, c: Condition): boolean {
  const blank = valueKey(v) === BLANK;
  if (c.op === "blank") return blank;
  if (c.op === "not_blank") return !blank;
  if (blank) return c.op === "ne" || c.op === "not_contains";

  if (kind === "number") {
    const x = Number(v);
    const a = Number(c.a);
    const b = Number(c.b);
    if (Number.isNaN(a)) return true;
    switch (c.op) {
      case "eq": return x === a;
      case "ne": return x !== a;
      case "gt": return x > a;
      case "ge": return x >= a;
      case "lt": return x < a;
      case "le": return x <= a;
      case "between": return x >= Math.min(a, b) && x <= Math.max(a, b);
      default: return true;
    }
  }

  if (kind === "date") {
    const d = String(v).slice(0, 10);
    const [lo, hi] = c.a <= c.b ? [c.a, c.b] : [c.b, c.a];
    switch (c.op) {
      case "eq": return d === c.a;
      case "ne": return d !== c.a;
      case "gt": return d > c.a;
      case "ge": return d >= c.a;
      case "lt": return d < c.a;
      case "le": return d <= c.a;
      case "between": return d >= lo && d <= hi;
      default: return true;
    }
  }

  const s = valueKey(v).toLowerCase();
  const a = c.a.toLowerCase();
  switch (c.op) {
    case "contains": return s.includes(a);
    case "not_contains": return !s.includes(a);
    case "eq": return s === a;
    case "ne": return s !== a;
    case "begins": return s.startsWith(a);
    case "ends": return s.endsWith(a);
    default: return true;
  }
}

export function isActive(f: ColumnFilter | undefined): f is ColumnFilter {
  return !!f && (f.values !== null || f.condition !== null);
}

/** Rows passing every column filter, optionally ignoring one column (Excel lists a column's values from the other filters). */
export function applyFilters(rows: Row[], filters: Filters, kinds: Record<string, ColumnKind>, except?: string): Row[] {
  const active = Object.entries(filters)
    .filter(([col, f]) => col !== except && isActive(f))
    .map(([col, f]) => ({ col, kind: kinds[col] ?? "text", values: f.values ? new Set(f.values) : null, condition: f.condition }));
  if (!active.length) return rows;
  return rows.filter((r) =>
    active.every(({ col, kind, values, condition }) => {
      const v = r[col];
      if (values && !values.has(valueKey(v))) return false;
      return !condition || matches(v, kind, condition);
    }),
  );
}

/** Distinct value keys with their counts, sorted the way Excel lists them (blanks last). */
export function distinctValues(rows: Row[], col: string, kind: ColumnKind): { key: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const r of rows) {
    const k = valueKey(r[col]);
    counts.set(k, (counts.get(k) ?? 0) + 1);
  }
  const out = [...counts].map(([key, count]) => ({ key, count }));
  out.sort((x, y) => {
    if (x.key === BLANK) return 1;
    if (y.key === BLANK) return -1;
    return kind === "number" ? Number(x.key) - Number(y.key) : x.key.localeCompare(y.key);
  });
  return out;
}

export function describeFilter(f: ColumnFilter, kind: ColumnKind, total: number): string {
  const parts: string[] = [];
  if (f.condition) {
    const label = OPS[kind].find((o) => o.op === f.condition!.op)?.label.toLowerCase() ?? f.condition.op;
    const { a, b } = f.condition;
    parts.push(f.condition.op === "between" ? `${label} ${a} and ${b}` : needsValue(f.condition.op) ? `${label} ${a}` : label);
  }
  if (f.values) {
    parts.push(f.values.length === 1 ? valueLabel(f.values[0], kind) : `${f.values.length} of ${total} values`);
  }
  return parts.join(" · ");
}
