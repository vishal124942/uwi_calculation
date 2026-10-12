import { inr, pct } from "./format";
import { rowsOf, sectionsOf } from "./trace";
import type { Cell, StepData, TransactionDelta } from "./types";

function column(delta: TransactionDelta | null, name: string): Cell[] {
  if (!delta) return [];
  const i = delta.columns.indexOf(name);
  return i < 0 ? [] : delta.rows.map((r) => r[i]);
}

/** One-line summary of what a finished step produced, shown in the live run and step headers. */
export function stepHeadline(step: StepData): string {
  const t = step.tables;
  switch (step.step) {
    case "step01_ingest_and_clean": {
      const channels = new Set(column(step.transactions, "s01_channel_family"));
      return `${step.transactions?.rows.length.toLocaleString("en-IN")} transactions canonicalised across ${channels.size} channel families`;
    }
    case "step02_data_quality_gate": {
      const rows = rowsOf(t.step02_dq_metrics);
      if (rows.some((r) => r.pipeline_hard_stop)) return `Hard stop: ${rows.flatMap((r) => (r.hard_stop_reasons as string[]) ?? []).join("; ")}`;
      const recon = Math.min(...rows.map((r) => (r.DQ02_TxnReconciliationPassRate as number) ?? 1));
      const months = Math.min(...rows.map((r) => (r.DQ10_HistoryMonths as number) ?? 0));
      return `Passed · balance reconciliation ${pct(recon)} · ${months.toFixed(1)} months of history`;
    }
    case "step03_transaction_evidence": {
      const entities = rowsOf(t.step03_entities);
      const deterministic = entities.filter((e) => e.identity_status === "DETERMINISTIC").length;
      return `${entities.length.toLocaleString("en-IN")} counterparty entities resolved (${deterministic.toLocaleString("en-IN")} deterministic)`;
    }
    case "step04_role_inference": {
      const rules = column(step.transactions, "s04_rules_applied").filter((r) => Array.isArray(r) && r.length).length;
      const changed = column(step.transactions, "s04_model_top_role").filter(
        (r, i) => r !== column(step.transactions, "s04_top_role")[i],
      ).length;
      return `Role probabilities for every transaction · ${rules.toLocaleString("en-IN")} touched by rules, ${changed} top roles changed by rules`;
    }
    case "step05_pairing_and_multi_account": {
      const edges = t.step05_pair_edges?.rows.length ?? 0;
      const changed = column(step.transactions, "s05_role_changed").filter(Boolean).length;
      return `${edges} flow pairs matched · ${changed} transaction roles updated from pair evidence`;
    }
    case "step06_aggregation_archetype_cash": {
      const windows = rowsOf(t.step06_window_totals);
      const full = windows[windows.length - 1];
      if (!full) return "Economic ledger built";
      const m = full.months as number;
      const per = (k: string) => inr((full[k] as number) / m);
      return `Monthly EOC ${per("eoc")} − COR ${per("cor")} = ROC ${per("roc")}`;
    }
    case "step07_risk_signals": {
      const s = sectionsOf(t.step07_risk_signals);
      return `Coverage risk ${s.s20_coverage?.risk} · trend ${s.s18_trend?.regime} · cycle ${s.s13_cycle?.status} · anomaly review ${s.s19_anomaly?.review_required ? "required" : "not required"}`;
    }
    case "step08_income_and_legal_attribution": {
      const s = sectionsOf(t.step08_sbci_and_legal);
      return `Sustainable business cash income ${inr(s.s21_sbci?.sbci_monthly)} / month · legal ${s.s16_legal_attribution?.status}`;
    }
    case "step09_uncertainty_and_policy": {
      const s = sectionsOf(t.step09_uncertainty_and_policy);
      const u = s.s22_uncertainty ?? {};
      const d = s.s21_policy_decision ?? {};
      return `Confidence ${pct(u.confidence)} · interval ${inr(u.lower)} – ${inr(u.upper)} · UWI ${inr(d.underwriting_income_monthly)} (${d.status})`;
    }
    case "step10_explain_and_audit": {
      const reasons = rowsOf(t.step10_reason_codes).filter((r) => r.code).length;
      return `Bridge reconciled · ${reasons} reason code${reasons === 1 ? "" : "s"} · ${t.step10_feature_vector?.rows.length ?? 0} registry features`;
    }
    default:
      return "";
  }
}
