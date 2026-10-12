import type { AnalysisResult, Cell, RequestSummary, RoleTrace, Row, StepData, Table, TraceEvent } from "./types";

export interface TraceState {
  status: "idle" | "running" | "done" | "error";
  source?: string;
  request?: RequestSummary;
  steps: Record<string, StepData>;
  /** Transaction ids in pipeline order (consolidated, time-ordered from step 3 on). */
  order: string[];
  /** Cumulative transaction rows: every column added by every finished step. Mutated in place; see `txnVersion`. */
  txns: Map<string, Row>;
  txnVersion: number;
  /** Columns each step added to the transaction table. */
  columnsByStep: Record<string, string[]>;
  result?: AnalysisResult;
  roleTrace?: Record<string, RoleTrace>;
  totalMs?: number;
  error?: string;
  startedAt?: number;
}

export const initialTrace = (): TraceState => ({
  status: "idle",
  steps: {},
  order: [],
  txns: new Map(),
  txnVersion: 0,
  columnsByStep: {},
});

export function startTrace(): TraceState {
  return { ...initialTrace(), status: "running", startedAt: performance.now() };
}

export function applyEvent(state: TraceState, event: TraceEvent): TraceState {
  switch (event.event) {
    case "start":
      return { ...state, source: event.source, request: event.request };
    case "step": {
      const { event: _ignored, ...data } = event;
      void _ignored;
      const next: TraceState = { ...state, steps: { ...state.steps, [data.step]: data } };
      const delta = data.transactions;
      if (delta) {
        const [, ...added] = delta.columns;
        const order: string[] = [];
        for (const row of delta.rows) {
          const id = row[0] as string;
          order.push(id);
          let target = state.txns.get(id);
          if (!target) {
            target = { transaction_id: id };
            state.txns.set(id, target);
          }
          added.forEach((c, i) => {
            target[c] = row[i + 1];
          });
        }
        next.order = order;
        next.txnVersion = state.txnVersion + 1;
        next.columnsByStep = { ...state.columnsByStep, [data.step]: added };
      }
      return next;
    }
    case "result":
      return { ...state, status: "done", result: event.result, roleTrace: event.role_trace, totalMs: event.total_ms };
    case "error":
      return { ...state, status: "error", error: event.detail };
  }
}

export function rowsOf(table: Table | undefined): Row[] {
  if (!table) return [];
  return table.rows.map((r) => Object.fromEntries(table.columns.map((c, i) => [c, r[i]])));
}

/** Key/value tables (columns section, key, value) grouped into one object per section. */
export function sectionsOf(table: Table | undefined): Record<string, Record<string, Cell>> {
  const out: Record<string, Record<string, Cell>> = {};
  if (!table) return out;
  for (const [section, key, value] of table.rows) {
    (out[section as string] ??= {})[String(key)] = value;
  }
  return out;
}

export function transactionRows(state: TraceState): Row[] {
  return state.order.map((id) => state.txns.get(id)!).filter(Boolean);
}
