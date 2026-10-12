"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchMeta, type RunInput, streamTrace } from "@/lib/api";
import { componentCode, componentStatuses } from "@/lib/components";
import { applyEvent, initialTrace, startTrace, type TraceState } from "@/lib/trace";
import type { Meta } from "@/lib/types";
import BusinessStory from "./BusinessStory";
import ComponentView from "./ComponentView";
import LiveRun from "./LiveRun";
import { useSpotlight } from "./motion";
import Overview from "./Overview";
import RoleDistribution from "./RoleDistribution";
import RunPanel from "./RunPanel";
import Sidebar, { type View } from "./Sidebar";
import TopBar from "./TopBar";
import TransactionDrawer from "./TransactionDrawer";
import TransactionExplorer from "./TransactionExplorer";

export default function Explorer() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [metaError, setMetaError] = useState<string | null>(null);
  const [trace, setTrace] = useState<TraceState>(initialTrace);
  const [view, setView] = useState<View>("start");
  const [selectedTxn, setSelectedTxn] = useState<string | null>(null);
  const [runScreen, setRunScreen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const loadMeta = useCallback(() => {
    const controller = new AbortController();
    setMetaError(null);
    fetchMeta(controller.signal)
      .then(setMeta)
      .catch((e: unknown) => {
        if (!controller.signal.aborted) setMetaError(e instanceof Error ? e.message : String(e));
      });
    return controller;
  }, []);

  useEffect(() => {
    const controller = loadMeta();
    return () => controller.abort();
  }, [loadMeta]);

  const run = useCallback(async (input: RunInput) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setSelectedTxn(null);
    setTrace(startTrace());
    setRunScreen(true);
    setView("overview");
    try {
      await streamTrace(input, (event) => setTrace((s) => applyEvent(s, event)), controller.signal);
      setTrace((s) => (s.status === "running" ? { ...s, status: "error", error: "stream ended before a result" } : s));
    } catch (e) {
      if (controller.signal.aborted) return;
      setTrace((s) => ({ ...s, status: "error", error: e instanceof Error ? e.message : String(e) }));
    }
  }, []);

  useEffect(() => () => abortRef.current?.abort(), []);
  useSpotlight();

  const showView = useCallback((v: View) => {
    if (v === "overview") setRunScreen(false);
    setView(v);
  }, []);
  const leaveRunScreen = useCallback(() => setRunScreen(false), []);

  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [view]);

  const component = meta?.components.find((c) => c.id === view);
  const statuses = componentStatuses(meta, trace);

  return (
    <div className="flex min-h-screen">
      <div className="aurora" aria-hidden />
      <Sidebar meta={meta} trace={trace} view={view} onView={showView} />
      <main className="min-w-0 flex-1">
        {view !== "start" && <TopBar trace={trace} />}
        <div className="mx-auto max-w-[1480px] px-6 py-6 lg:px-8">
          <select
            aria-label="Navigate"
            value={view}
            onChange={(e) => showView(e.target.value)}
            className="mb-4 w-full rounded-lg border border-white/10 bg-ink-850 px-3 py-2 text-sm lg:hidden"
          >
            <option value="start">New analysis</option>
            <option value="overview" disabled={trace.status === "idle"}>Result overview</option>
            <option value="story" disabled={!trace.result?.underwriting}>Business story</option>
            <option value="roles" disabled={!trace.steps.step04_role_inference}>Role distribution</option>
            <option value="transactions" disabled={!trace.order.length}>Transaction journey</option>
            {meta?.components.map((c) => (
              <option key={c.id} value={c.id} disabled={statuses[c.id] !== "done"}>
                {componentCode(c)} · {c.name}
              </option>
            ))}
          </select>
          <div key={view === "overview" && (runScreen || !trace.result?.underwriting) ? "run" : view} className="view-enter">
            {view === "start" && <RunPanel meta={meta} metaError={metaError} onRetry={loadMeta} onRun={run} busy={trace.status === "running"} />}
            {view === "overview" &&
              (trace.status === "done" && trace.result?.underwriting && !runScreen ? (
                <Overview trace={trace} meta={meta} onView={showView} onOpenTxn={setSelectedTxn} />
              ) : (
                <LiveRun trace={trace} meta={meta} onView={showView} onRestart={() => showView("start")} onContinue={leaveRunScreen} />
              ))}
            {view === "story" && trace.result?.underwriting && <BusinessStory trace={trace} meta={meta} onOpenTxn={setSelectedTxn} onView={showView} />}
            {view === "roles" && <RoleDistribution trace={trace} meta={meta} onOpenTxn={setSelectedTxn} />}
            {view === "transactions" && <TransactionExplorer trace={trace} meta={meta} selected={selectedTxn} onOpenTxn={setSelectedTxn} />}
            {component && <ComponentView key={component.id} component={component} trace={trace} meta={meta} onOpenTxn={setSelectedTxn} onView={showView} />}
          </div>
        </div>
      </main>
      {selectedTxn && <TransactionDrawer id={selectedTxn} trace={trace} meta={meta} onClose={() => setSelectedTxn(null)} />}
    </div>
  );
}
