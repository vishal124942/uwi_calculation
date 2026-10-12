import { num } from "./format";
import { sectionsOf, transactionRows, type TraceState } from "./trace";
import type { Cell, Row } from "./types";

export const isCredit = (r: Row) => String(r.direction ?? "").toUpperCase().startsWith("C");

export interface DayFlow {
  date: string;
  credits: number;
  debits: number;
  count: number;
}

/** Credits and debits per booking date, every calendar day of the statement included. */
export function dailyFlows(trace: TraceState): DayFlow[] {
  const byDay = new Map<string, DayFlow>();
  let first = "";
  let last = "";
  for (const r of transactionRows(trace)) {
    const date = String(r.booking_date ?? "");
    const amount = num(r.amount);
    if (!date || amount === null) continue;
    const d = byDay.get(date) ?? { date, credits: 0, debits: 0, count: 0 };
    if (isCredit(r)) d.credits += amount;
    else d.debits += amount;
    d.count += 1;
    byDay.set(date, d);
    if (!first || date < first) first = date;
    if (!last || date > last) last = date;
  }
  if (!first) return [];
  const out: DayFlow[] = [];
  for (let t = Date.parse(`${first}T00:00:00Z`); t <= Date.parse(`${last}T00:00:00Z`); t += 86_400_000) {
    const date = new Date(t).toISOString().slice(0, 10);
    out.push(byDay.get(date) ?? { date, credits: 0, debits: 0, count: 0 });
  }
  return out;
}

export interface Counterparty {
  id: string;
  name: string;
  credit: number;
  debit: number;
  count: number;
  months: number;
  /** Final role carrying most of the counterparty's money. */
  role: string | null;
  largestTxn: string;
}

const titleCase = (s: string) => s.toLowerCase().replace(/\b[a-z]/g, (c) => c.toUpperCase());

const UPI_HANDLE = /^(ok[a-z]+|paytm|ibl|ybl|axl|apl|upi)$/i;

function withoutUpiHandle(name: string): string {
  const words = name.split(/\s+/).filter(Boolean);
  const kept = words.filter((w) => !UPI_HANDLE.test(w));
  return (kept.length ? kept : words).join(" ");
}

function nameOf(label: Cell, tokens: Map<string, number>, narration: string): string {
  if (typeof label === "string" && label.trim()) return titleCase(withoutUpiHandle(label));
  const best = [...tokens.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];
  if (best) return titleCase(withoutUpiHandle(best));
  return narration.slice(0, 28) || "Unnamed";
}

/** Counterparty entities (M2 entity resolution) with their money in and out. */
export function counterparties(trace: TraceState): Counterparty[] {
  const acc = new Map<
    string,
    { label: Cell; tokens: Map<string, number>; roles: Map<string, number>; credit: number; debit: number; count: number; months: Cell; narration: string; largest: [string, number] }
  >();
  for (const r of transactionRows(trace)) {
    const id = r.s03_entity_cluster_id;
    const amount = num(r.amount);
    if (typeof id !== "string" || amount === null) continue;
    let e = acc.get(id);
    if (!e) {
      e = { label: r.s03_entity_label, tokens: new Map(), roles: new Map(), credit: 0, debit: 0, count: 0, months: r.s03_entity_active_months, narration: String(r.normalized_narration ?? ""), largest: [String(r.transaction_id), -1] };
      acc.set(id, e);
    }
    if (isCredit(r)) e.credit += amount;
    else e.debit += amount;
    e.count += 1;
    if (amount > e.largest[1]) e.largest = [String(r.transaction_id), amount];
    const tokens = Array.isArray(r.s03_id_name_tokens) ? (r.s03_id_name_tokens as Cell[]).map(String).join(" ") : "";
    if (tokens) e.tokens.set(tokens, (e.tokens.get(tokens) ?? 0) + 1);
    const role = r.s05_top_role ?? r.s04_top_role;
    if (typeof role === "string") e.roles.set(role, (e.roles.get(role) ?? 0) + amount);
  }
  return [...acc.entries()].map(([id, e]) => ({
    id,
    name: nameOf(e.label, e.tokens, e.narration),
    credit: e.credit,
    debit: e.debit,
    count: e.count,
    months: num(e.months) ?? 0,
    role: [...e.roles.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null,
    largestTxn: e.largest[0],
  }));
}

/** Key/value sections of the step 7 risk-signal table (s13_cycle, s14_liquidity, s16_owner, s19_anomaly, ...). */
export function riskSignals(trace: TraceState): Record<string, Record<string, Cell>> {
  return sectionsOf(trace.steps.step07_risk_signals?.tables.step07_risk_signals);
}
