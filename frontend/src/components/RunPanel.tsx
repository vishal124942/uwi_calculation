"use client";

import { ArrowRight, FileUp, FlaskConical, Play, RefreshCw, ServerCrash, Trash2 } from "lucide-react";
import { useRef, useState } from "react";
import { API_BASE, type RunInput, type RunOptions } from "@/lib/api";
import type { Meta } from "@/lib/types";
import { ComponentChip } from "./ComponentView";
import { Card, cx } from "./ui";

const ACCEPT = ".xlsx,.xlsm,.csv";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[11px] font-medium uppercase tracking-wider text-ink-400">{label}</span>
      {children}
    </label>
  );
}

const inputClass =
  "w-full rounded-lg border border-white/[0.08] bg-ink-850 px-3 py-2 text-sm text-ink-100 focus:border-sky-400/50 focus:outline-none";

export default function RunPanel({
  meta,
  metaError,
  onRetry,
  onRun,
  busy,
}: {
  meta: Meta | null;
  metaError: string | null;
  onRetry: () => void;
  onRun: (input: RunInput) => void;
  busy: boolean;
}) {
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [options, setOptions] = useState<RunOptions>({
    legalOwnerType: "SOLE_PROP",
    accountType: "SAVINGS",
    policyId: "SE_INCOME_POLICY_001",
    asOfDate: "",
    customerId: "",
    applicationId: "",
  });
  const inputRef = useRef<HTMLInputElement>(null);
  const set = (patch: Partial<RunOptions>) => setOptions((o) => ({ ...o, ...patch }));

  const addFiles = (list: FileList | null) => {
    if (!list) return;
    const accepted = Array.from(list).filter((f) => /\.(xlsx|xlsm|csv)$/i.test(f.name));
    setFiles((prev) => [...prev, ...accepted.filter((f) => !prev.some((p) => p.name === f.name && p.size === f.size))]);
  };

  return (
    <div className="rise space-y-8">
      <div className="pt-6">
        <div className="text-xs font-semibold uppercase tracking-[0.2em] text-sky-300/80">Self-employed income reconstruction</div>
        <h1 className="mt-3 max-w-3xl text-4xl font-semibold leading-tight tracking-tight text-ink-100">
          Watch a bank statement become an <span className="bg-gradient-to-r from-sky-300 to-violet-300 bg-clip-text text-transparent">underwriting income</span>, M1 to M9.
        </h1>
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-ink-300">
          Upload a statement and the engine runs live, organised by the specification&apos;s component architecture: M1 parser, M2 role
          classifier, M3 rule overlay, M4 flow pairs, M5 archetype, M6 cycle, M7 income estimator, M8 uncertainty and M9 policy. Each
          component shows the exact calculations it performed on this statement, and you can follow any single transaction through them.
        </p>
      </div>

      {metaError && (
        <Card className="border-rose-400/20 bg-rose-400/[0.04]">
          <div className="flex flex-wrap items-start gap-4 p-5">
            <ServerCrash className="mt-0.5 h-5 w-5 text-rose-300" />
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold text-rose-200">Cannot reach the engine API at {API_BASE}</div>
              <p className="mt-1 text-xs text-ink-300">Start it from the repository root, then retry:</p>
              <pre className="mt-2 overflow-x-auto rounded-lg bg-ink-950 px-3 py-2 font-mono text-xs text-ink-200">.venv/bin/uvicorn se_income_engine.api.app:app --reload</pre>
              <p className="mt-2 text-[11px] text-ink-400">{metaError}</p>
            </div>
            <button onClick={onRetry} className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-xs hover:bg-white/5">
              <RefreshCw className="h-3.5 w-3.5" /> Retry
            </button>
          </div>
        </Card>
      )}

      <div className="grid gap-6 xl:grid-cols-[1.4fr_1fr]">
        <Card>
          <div className="p-6">
            <div className="mb-4 flex items-center gap-2 text-sm font-semibold">
              <FileUp className="h-4 w-4 text-sky-300" /> Analyse your statements
            </div>
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                addFiles(e.dataTransfer.files);
              }}
              onClick={() => inputRef.current?.click()}
              className={cx(
                "flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-10 text-center transition",
                dragging ? "border-sky-400/60 bg-sky-400/[0.06]" : "border-white/10 hover:border-white/20 hover:bg-white/[0.02]",
              )}
            >
              <FileUp className="h-8 w-8 text-ink-400" />
              <div className="mt-3 text-sm text-ink-200">Drop analyser .xlsx / .xlsm or generic .csv statements</div>
              <div className="mt-1 text-xs text-ink-400">Several files are consolidated as one multi-account borrower (Section 17)</div>
              <input ref={inputRef} type="file" multiple accept={ACCEPT} className="hidden" onChange={(e) => addFiles(e.target.files)} />
            </div>

            {files.length > 0 && (
              <ul className="mt-4 space-y-1.5">
                {files.map((f) => (
                  <li key={f.name + f.size} className="flex items-center gap-3 rounded-lg bg-white/[0.03] px-3 py-2 text-xs">
                    <span className="flex-1 truncate text-ink-100">{f.name}</span>
                    <span className="text-ink-400 tabular">{(f.size / 1024).toFixed(0)} KB</span>
                    <button onClick={() => setFiles((p) => p.filter((x) => x !== f))} className="text-ink-400 hover:text-rose-300" aria-label={`Remove ${f.name}`}>
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </li>
                ))}
              </ul>
            )}

            <div className="mt-5 grid gap-4 sm:grid-cols-3">
              <Field label="Legal owner type">
                <select className={inputClass} value={options.legalOwnerType} onChange={(e) => set({ legalOwnerType: e.target.value })}>
                  {(meta?.legal_owner_types ?? ["SOLE_PROP"]).map((v) => <option key={v}>{v}</option>)}
                </select>
              </Field>
              <Field label="Account type">
                <select className={inputClass} value={options.accountType} onChange={(e) => set({ accountType: e.target.value })}>
                  {(meta?.account_types ?? ["SAVINGS"]).map((v) => <option key={v}>{v}</option>)}
                </select>
              </Field>
              <Field label="Policy">
                <select className={inputClass} value={options.policyId} onChange={(e) => set({ policyId: e.target.value })}>
                  {(meta?.policies ?? []).map((p) => <option key={p.policy_id} value={p.policy_id}>{p.policy_id} v{p.policy_version}</option>)}
                </select>
              </Field>
              <Field label="As-of date (optional)">
                <input type="date" className={inputClass} value={options.asOfDate} onChange={(e) => set({ asOfDate: e.target.value })} />
              </Field>
              <Field label="Customer id (optional)">
                <input className={inputClass} value={options.customerId} placeholder="UI-CUSTOMER" onChange={(e) => set({ customerId: e.target.value })} />
              </Field>
              <Field label="Application id (optional)">
                <input className={inputClass} value={options.applicationId} placeholder="UI-APPLICATION" onChange={(e) => set({ applicationId: e.target.value })} />
              </Field>
            </div>

            <button
              disabled={!files.length || busy || !meta}
              onClick={() => onRun({ kind: "upload", files, options })}
              className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-sky-400 to-violet-400 px-4 py-3 text-sm font-semibold text-ink-950 shadow-lg shadow-sky-500/10 transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Play className="h-4 w-4" /> Run the pipeline
            </button>
            <p className="mt-2 text-center text-[11px] text-ink-400">Files are processed by your local engine API only; trace runs are not written to the audit store.</p>
          </div>
        </Card>

        <div className="space-y-6">
          <Card>
            <div className="p-6">
              <div className="mb-1 flex items-center gap-2 text-sm font-semibold">
                <FlaskConical className="h-4 w-4 text-violet-300" /> No statement at hand? Run a synthetic one
              </div>
              <p className="mb-4 text-xs text-ink-400">Generated by the same builder the test suite uses (Section 27.2 synthetic golden statements).</p>
              <div className="space-y-2.5">
                {Object.entries(meta?.demo_scenarios ?? {}).map(([key, description]) => (
                  <button
                    key={key}
                    disabled={busy}
                    onClick={() => onRun({ kind: "demo", scenario: key, options })}
                    className="group flex w-full items-center gap-3 rounded-xl border border-white/[0.07] bg-white/[0.02] px-4 py-3 text-left transition hover:border-violet-400/30 hover:bg-violet-400/[0.05] disabled:opacity-40"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="font-mono text-xs font-semibold text-violet-200">{key}</div>
                      <div className="mt-0.5 text-xs text-ink-300">{description}</div>
                    </div>
                    <ArrowRight className="h-4 w-4 text-ink-400 transition group-hover:translate-x-0.5 group-hover:text-violet-200" />
                  </button>
                ))}
                {!meta && !metaError && <div className="h-24 animate-pulse rounded-xl bg-white/[0.03]" />}
              </div>
            </div>
          </Card>

          <Card>
            <div className="p-6">
              <div className="text-sm font-semibold">How the components work together</div>
              <div className="mb-3 mt-0.5 text-xs text-ink-400">Section 24.1 architecture: M1–M9 and the supporting stages between them, in execution order</div>
              <ol className="space-y-2">
                {(meta?.components ?? []).map((c) => (
                  <li key={c.id} className="grid grid-cols-[3.5rem_1fr] gap-3 text-xs">
                    <ComponentChip c={c} className="mt-px w-full" />
                    <span>
                      <span className={c.kind === "model" ? "text-ink-100" : "text-ink-300"}>{c.name}</span>
                      <span className="ml-1.5 text-ink-400">{c.responsibility}</span>
                    </span>
                  </li>
                ))}
              </ol>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
