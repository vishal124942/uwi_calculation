"use client";

import { useMemo } from "react";
import { cellText, fixed, inr, pct } from "@/lib/format";
import { rowsOf, sectionsOf } from "@/lib/trace";
import type { Cell } from "@/lib/types";
import type { StepProps } from "./shared";
import { Legend, SeriesChart } from "../charts";
import { Badge, CalcLine, Card, CardBody, CardHeader, Formula, KeyValueGrid, riskTone, type Tone } from "../ui";

const MONEY = /Balance|Outflow|Amount|monthly|ROC|Need|Draw$|ExpectedOwnerDraw|Median Monthly|EOC$|COR$|threshold|MassAmount|OwnTransferMass|normal_monthly|normalisation_amount|LiquidityNeed/;
const RATIO = /Ratio|Share|Rate|Retention|Coverage|Quality|Score|Index|Dependency|Contamination|Concentration|Consistency|Correlation|Prominence|Stability|Strength|Utilisation|UTIL|Intensity|Visibility|Fragmentation|Suspicion|Link|_vs_/;

function format(k: string, v: Cell): string {
  if (typeof v !== "number") return cellText(v);
  if (/Lag|Days|Count|months|weeks|Weeks|LIMIT_BREACH|account_count|ActiveMonths/.test(k)) return fixed(v, /Lag|Days/.test(k) ? 1 : 0);
  if (MONEY.test(k) && Math.abs(v) >= 10) return inr(v);
  if (RATIO.test(k) && Math.abs(v) <= 5) return /_vs_|Index/.test(k) ? `${v.toFixed(3)}×` : pct(v);
  return cellText(v);
}

function Section({ title, subtitle, badge, data, children }: { title: string; subtitle: string; badge?: { text: string; tone: Tone }; data: Record<string, Cell>; children?: React.ReactNode }) {
  return (
    <Card>
      <CardHeader title={title} subtitle={subtitle} right={badge && <Badge tone={badge.tone}>{badge.text}</Badge>} />
      <CardBody className="space-y-4">
        {children}
        <KeyValueGrid data={data} format={format} />
      </CardBody>
    </Card>
  );
}

/** Pipeline step 7 is shared: part "cycle" is M6, part "signals" is the behaviour and risk feature engines. */
export default function Step07({ data, part }: StepProps) {
  const s = sectionsOf(data.tables.step07_risk_signals);
  const balance = useMemo(() => rowsOf(data.tables.step07_daily_balance), [data]);
  const lags = useMemo(() => rowsOf(data.tables.step07_cycle_lag_profile), [data]);
  const financingEvents = rowsOf(data.tables.step07_financing_events);
  const accounts = useMemo(() => [...new Set(balance.map((b) => String(b.account_id)))], [balance]);
  const balanceSeries = useMemo(() => {
    const byDay = new Map<string, Record<string, Cell>>();
    for (const b of balance) {
      const d = String(b.day);
      const row = byDay.get(d) ?? { day: d };
      row[String(b.account_id)] = b.balance;
      byDay.set(d, row);
    }
    return [...byDay.values()];
  }, [balance]);
  const palette = ["#38bdf8", "#a78bfa", "#34d399", "#fbbf24"];

  const { status: cycleStatus, notes: cycleNotes, ...cycle } = s.s13_cycle ?? {};
  const { regime, ...trend } = s.s18_trend ?? {};
  const { risk, ...coverage } = s.s20_coverage ?? {};
  const { review_required, triggers, ...anomaly } = s.s19_anomaly ?? {};

  const cycleSection = (
    <Section
      title="Working-capital cycle (Section 13)"
      subtitle="Cross-correlation of weekly purchases and collections; build-up or liquidation near the statement end is normalised by M7 (ROC → CAOCG)"
      badge={{ text: String(cycleStatus ?? "—"), tone: cycleStatus === "IDENTIFIED" ? "good" : "warn" }}
      data={cycle}
    >
      {part === "cycle" && (
        <>
          <Formula>
            ρ(k) = Spearman( weekly direct purchases(t), weekly EOC(t + k) ), k = 0 … max lag weeks (≥ 6 overlapping weeks)
            <br />
            IDENTIFIED if peak ρ ≥ min strength and prominence = ρ(peak) − mean ρ(peak ± 1, 2) ≥ min prominence; otherwise WEAK_OR_UNIDENTIFIED (no default)
            <br />
            conversion = Σ EOC ÷ Σ direct purchases &nbsp;·&nbsp; only if 1 ≤ conversion ≤ 3, over the last r = max(peak lag days, 14) days:
            <br />
            build = min(cap, purchases_r − EOC_r ÷ conversion) &nbsp;·&nbsp; liquidation = min(cap, (EOC_r − conversion × purchases_r) ÷ conversion) &nbsp;·&nbsp; cap ∝ normal monthly EOC × r ÷ 30.4
          </Formula>
          <div className="rounded-xl bg-white/[0.02] px-4 py-2">
            <CalcLine label="peak purchase → collection lag (WC01)" value={cycle.WC01_PeakOutflowToInflowLag == null ? "none" : `${fixed(cycle.WC01_PeakOutflowToInflowLag, 0)} days`} />
            <CalcLine label="peak correlation ρ (WC03)" value={fixed(cycle.WC03_CycleCorrelation, 3)} note={`prominence ${fixed(cycle.WC04_CycleProminence, 3)}`} />
            <CalcLine label="conversion ratio" value={fixed(cycle.conversion_ratio, 3)} note="collections per rupee of purchases" />
            <CalcLine label="normal monthly EOC" value={inr(cycle.normal_monthly_eoc)} />
            <CalcLine label="build normalisation" value={inr(cycle.build_normalisation_amount, 2)} />
            <CalcLine op="−" label="liquidation normalisation" value={inr(cycle.liquidation_normalisation_amount, 2)} />
            <CalcLine
              op="="
              label="net cycle adjustment handed to M7 (ROC → CAOCG)"
              value={inr(((cycle.build_normalisation_amount as number) ?? 0) - ((cycle.liquidation_normalisation_amount as number) ?? 0), 2)}
              emphasis
            />
          </div>
        </>
      )}
      <Legend items={[{ label: "purchases → collections", color: "#34d399" }, { label: "collections → purchases", color: "#fbbf24" }]} />
      <SeriesChart
        data={lags}
        xKey="lag_weeks"
        height={part === "cycle" ? 260 : 200}
        formatY={(v) => v.toFixed(2)}
        formatValue={(v) => v.toFixed(3)}
        series={[
          { key: "purchases_to_collections", label: "purchases → collections", color: "#34d399", type: "bar" },
          { key: "collections_to_purchases", label: "collections → purchases", color: "#fbbf24", type: "bar" },
        ]}
      />
      {Array.isArray(cycleNotes) && cycleNotes.length > 0 && <div className="text-xs text-ink-300">{cycleNotes.join(" · ")}</div>}
    </Section>
  );

  if (part === "cycle") return <div className="space-y-6">{cycleSection}</div>;

  return (
    <div className="space-y-6">
      <div className={part ? "" : "grid gap-6 xl:grid-cols-2"}>
        <Section title="Balance and liquidity (Section 14)" subtitle="Daily end-of-day balance, buffers against COR, how much of each receipt stays in the account" data={s.s14_liquidity ?? {}}>
          <Legend items={accounts.map((a, i) => ({ label: a, color: palette[i % palette.length] }))} />
          <SeriesChart
            data={balanceSeries}
            xKey="day"
            height={220}
            series={accounts.map((a, i) => ({ key: a, label: a, color: palette[i % palette.length], type: "area" as const }))}
          />
        </Section>
        {!part && cycleSection}
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Section title="Financing and debt service (Section 15)" subtitle="Loan credits, EMI / interest / principal outflows and external funding dependency" data={s.s15_financing ?? {}}>
          {financingEvents.length > 0 && (
            <div className="text-xs text-ink-300">
              Financing events: {financingEvents.map((e) => `${String(e.date)} ${inr(e.amount)}`).join(" · ")}
            </div>
          )}
        </Section>
        <Section title="Owner extraction (Section 16.1)" subtitle="Draws by the owner: corroborate income, but never define it" data={s.s16_owner ?? {}} />
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Section
          title="Trend and seasonality (Section 18)"
          subtitle="Asymmetric: decline is believed quickly, growth needs corroboration"
          badge={{ text: String(regime ?? "—"), tone: regime === "DECLINE" ? "bad" : regime === "STABLE" ? "good" : "info" }}
          data={trend}
        />
        <Section
          title="Coverage and observability (Section 20)"
          subtitle="Signs that business activity happens outside the supplied accounts"
          badge={{ text: `${String(risk ?? "—")} risk`, tone: riskTone(String(risk)) }}
          data={coverage}
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Section
          title="Anomaly and window-dressing detection (Section 19)"
          subtitle="Pre-application surges, recycling, round amounts, statement-end effects"
          badge={{ text: review_required ? "review required" : "no review", tone: review_required ? "bad" : "good" }}
          data={anomaly}
        >
          {Array.isArray(triggers) && triggers.length > 0 && (
            <div className="flex flex-wrap gap-1.5">{triggers.map((t) => <Badge key={String(t)} tone="bad">{String(t)}</Badge>)}</div>
          )}
        </Section>
        <div className="space-y-6">
          <Section title="Multi-account consolidation (Section 17)" subtitle="Matched internal transfers, fragmentation and missing-account evidence" data={s.s17_multi_account ?? {}} />
          <Section
            title="Amount-weighted role uncertainty (Section 22.2)"
            subtitle="Σ amount × max(entropy, P(unknown)) ÷ Σ amount; feeds the M8 role-certainty dimension CF03"
            data={s.s22_role_uncertainty ?? {}}
          />
        </div>
      </div>
    </div>
  );
}
