export type Cell = string | number | boolean | null | Cell[] | { [key: string]: Cell };
export type Row = Record<string, Cell>;

export interface Table {
  columns: string[];
  rows: Cell[][];
}

export interface TransactionDelta extends Table {
  table: string;
}

export interface ModuleMeta {
  name: string;
  doc: string;
}

/** A pipeline execution checkpoint; the trace streams one step event per checkpoint. */
export interface StepMeta {
  id: string;
  number: number;
  title: string;
  sections: string;
  modules: (ModuleMeta & { component: string })[];
}

export type ComponentKind = "model" | "gate" | "features" | "output";

/** A Section 24.1 component (M1–M9) or a labelled supporting stage, with the engine modules that implement it. */
export interface ComponentMeta {
  id: string;
  kind: ComponentKind;
  name: string;
  sections: string;
  technique: string;
  responsibility: string;
  /** Code package, e.g. "services/m1_parser_normaliser". */
  package: string;
  modules: (ModuleMeta & { path: string; step: string })[];
  /** Execution checkpoints the modules finish in, in order. */
  steps: string[];
}

export interface Policy {
  policy_id: string;
  policy_version: string;
  estimate_basis: string;
  blend_weight_central: number;
  lower_quantile: number;
  upper_quantile: number;
  min_confidence_auto_decision: number;
  deterioration_force_lower_bound: number;
  refer_on_high_coverage_risk: boolean;
  refer_on_anomaly: boolean;
  rounding_unit: number;
}

export interface Meta {
  version: string;
  steps: StepMeta[];
  components: ComponentMeta[];
  roles: Record<string, string>;
  archetypes: Record<string, string>;
  policies: Policy[];
  account_types: string[];
  legal_owner_types: string[];
  demo_scenarios: Record<string, string>;
  model_versions: Record<string, string>;
}

export interface AccountSummary {
  account_id: string;
  account_type: string;
  legal_owner_type: string;
  statement_start: string;
  statement_end: string;
  transactions: number;
  bank: string | null;
  holder_name: string | null;
  masked_account: string | null;
  source_file: string | null;
}

export interface RequestSummary {
  customer_id: string;
  application_id: string;
  as_of_date: string;
  policy_id: string;
  legal_owner_type: string;
  accounts: AccountSummary[];
}

export interface StepData {
  step: string;
  compute_ms: number;
  tables: Record<string, Table>;
  transactions: TransactionDelta | null;
  detail: Record<string, Cell>;
}

export interface RoleAdjustment {
  rule_id: string;
  rule_version: string;
  action: string;
  roles: Record<string, number>;
  description: string;
}

export interface RoleTrace {
  model: Record<string, number>;
  calibrated: Record<string, number>;
  after_rules: Record<string, number>;
  rules: RoleAdjustment[];
  final?: Record<string, number>;
  pair_adjustments?: RoleAdjustment[];
  entropy?: number;
}

export interface BridgeLine {
  line: string;
  monthly_amount: number;
  kind: "TOTAL" | "DEDUCTION" | "SUBTOTAL" | "ADJUSTMENT" | "RESULT" | "MEMO" | "POLICY";
  note: string;
}

export interface ReasonCode {
  code: string;
  reason: string;
  meaning: string;
  evidence: Record<string, Cell>;
}

export interface MonthlyPoint {
  month: string;
  coverage: number;
  complete: boolean;
  gross_credits: number;
  eoc: number;
  cor: number;
  roc: number;
  caocg: number;
  financing_in: number;
  debt_service: number;
  owner_draw: number;
}

export interface EvidenceTxn {
  transaction_id: string;
  date: string;
  amount: number;
  contribution?: number;
  top_role: string;
  top_probability?: number;
  channel?: string;
  direction?: string;
  entropy?: number;
}

export interface AnalysisResult {
  analysis_id: string;
  status: string;
  economic_outputs: Record<string, number | string | null> | null;
  underwriting: {
    underwriting_income_monthly: number | null;
    central_estimate: number;
    lower_bound: number;
    upper_bound: number;
    confidence: number;
    coverage_risk: string;
    legal_attribution_status: string;
    borrower_income_monthly: number | null;
    selection_basis: string;
    interval_method: string;
    unresolved_outflow_allowance_monthly: number;
    unresolved_inflow_allowance_monthly: number;
    referral_reasons: string[];
  } | null;
  bridge?: BridgeLine[];
  reasons: ReasonCode[];
  drivers: Row[];
  flags: string[];
  confidence_dimensions?: Record<string, number>;
  archetype?: { code: string; probability: number; probabilities: Record<string, number> };
  cycle?: Record<string, Cell>;
  trend?: Record<string, Cell>;
  monthly_series?: MonthlyPoint[];
  role_mix_full_period?: Record<string, number>;
  pass_through?: Record<string, Cell>;
  data_quality: Record<string, Record<string, Cell>>;
  transaction_evidence?: Record<string, EvidenceTxn[]>;
  model_versions: Record<string, string>;
  policy_version: string;
  transaction_count?: number;
  role_uncertainty?: number;
}

export type TraceEvent =
  | { event: "start"; source: string; request: RequestSummary }
  | ({ event: "step" } & StepData)
  | { event: "result"; result: AnalysisResult; role_trace: Record<string, RoleTrace>; total_ms: number }
  | { event: "error"; detail: string };
