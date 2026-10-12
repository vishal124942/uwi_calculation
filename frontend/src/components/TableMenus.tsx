"use client";

import { ArrowDownWideNarrow, ArrowUpNarrowWide, FilterX, Search } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  type ColumnFilter,
  type ColumnKind,
  distinctValues,
  isActive,
  isComplete,
  needsValue,
  type Op,
  OPS,
  valueLabel,
} from "@/lib/tableFilter";
import type { Row } from "@/lib/types";
import { cx } from "./ui";

const MAX_LISTED = 500;

const SORT_LABELS: Record<ColumnKind, [string, string]> = {
  number: ["Sort smallest to largest", "Sort largest to smallest"],
  date: ["Sort oldest to newest", "Sort newest to oldest"],
  text: ["Sort A to Z", "Sort Z to A"],
  boolean: ["Sort no to yes", "Sort yes to no"],
};

const FILTER_LABEL: Record<ColumnKind, string> = {
  number: "Number filter",
  date: "Date filter",
  text: "Text filter",
  boolean: "",
};

const INPUT =
  "w-full rounded-md border border-white/[0.08] bg-ink-850 px-2 py-1.5 text-xs text-ink-100 placeholder:text-ink-400 focus:border-sky-400/50 focus:outline-none [color-scheme:dark]";

/** Fixed-position menu under an anchor; buttons marked data-menu-anchor toggle it instead of counting as outside clicks. */
export function Popover({ anchor, width, onClose, children }: { anchor: DOMRect; width: number; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const outside = (e: Event) => {
      const target = e.target as Element | null;
      if (ref.current?.contains(target) || target?.closest?.("[data-menu-anchor]")) return;
      onClose();
    };
    const key = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      // Capture phase: Escape closes only the menu, not the full panel or drawer behind it.
      e.stopImmediatePropagation();
      onClose();
    };
    document.addEventListener("mousedown", outside);
    window.addEventListener("keydown", key, true);
    window.addEventListener("scroll", outside, true);
    window.addEventListener("resize", onClose);
    return () => {
      document.removeEventListener("mousedown", outside);
      window.removeEventListener("keydown", key, true);
      window.removeEventListener("scroll", outside, true);
      window.removeEventListener("resize", onClose);
    };
  }, [onClose]);

  const below = window.innerHeight - anchor.bottom;
  const flip = below < 340 && anchor.top > below;
  const left = Math.max(8, Math.min(anchor.left, window.innerWidth - width - 8));
  const style = flip
    ? { left, width, bottom: window.innerHeight - anchor.top + 4, maxHeight: anchor.top - 12 }
    : { left, width, top: anchor.bottom + 4, maxHeight: below - 12 };

  return createPortal(
    <div
      ref={ref}
      style={style}
      className="fixed z-50 flex flex-col overflow-hidden rounded-xl border border-white/10 bg-ink-850 text-xs text-ink-200 shadow-2xl shadow-black/60"
    >
      {children}
    </div>,
    document.body,
  );
}

export function FilterMenu({
  col,
  kind,
  anchor,
  rows,
  filter,
  sortDir,
  onSort,
  onApply,
  onClose,
}: {
  col: string;
  kind: ColumnKind;
  anchor: DOMRect;
  /** Rows passing every other column's filter. */
  rows: Row[];
  filter?: ColumnFilter;
  sortDir: 1 | -1 | null;
  onSort: (dir: 1 | -1) => void;
  onApply: (filter: ColumnFilter | null) => void;
  onClose: () => void;
}) {
  const values = useMemo(() => distinctValues(rows, col, kind), [rows, col, kind]);
  const [selected, setSelected] = useState<Set<string>>(() => new Set(filter?.values ?? values.map((v) => v.key)));
  const [search, setSearch] = useState("");
  const [op, setOp] = useState<Op | "">(filter?.condition?.op ?? "");
  const [a, setA] = useState(filter?.condition?.a ?? "");
  const [b, setB] = useState(filter?.condition?.b ?? "");

  const q = search.trim().toLowerCase();
  const matching = useMemo(
    () => (q ? values.filter((v) => valueLabel(v.key, kind).toLowerCase().includes(q) || v.key.toLowerCase().includes(q)) : values),
    [values, q, kind],
  );
  const listed = matching.slice(0, MAX_LISTED);
  const checkedCount = matching.filter((v) => selected.has(v.key)).length;
  const anySelected = values.some((v) => selected.has(v.key));

  const toggle = (key: string) =>
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  const toggleMatching = () =>
    setSelected((s) => {
      const next = new Set(s);
      const add = checkedCount < matching.length;
      for (const v of matching) {
        if (add) next.add(v.key);
        else next.delete(v.key);
      }
      return next;
    });

  const apply = () => {
    const all = values.every((v) => selected.has(v.key));
    const keys = all ? null : values.filter((v) => selected.has(v.key)).map((v) => v.key);
    const condition = op && isComplete({ op, a, b }) ? { op, a, b } : null;
    onApply(keys === null && condition === null ? null : { values: keys, condition });
    onClose();
  };

  const inputType = kind === "number" ? "number" : kind === "date" ? "date" : "text";
  const [ascLabel, descLabel] = SORT_LABELS[kind];

  return (
    <Popover anchor={anchor} width={300} onClose={onClose}>
      <form
        className="flex min-h-0 flex-col"
        onSubmit={(e) => {
          e.preventDefault();
          if (anySelected) apply();
        }}
      >
        <div className="flex items-center justify-between gap-2 border-b border-white/[0.06] px-3 py-2">
          <span className="truncate font-mono text-[11px] text-ink-100" title={col}>
            {col}
          </span>
          <span className="shrink-0 rounded bg-white/[0.06] px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-ink-400">{kind}</span>
        </div>

        <div className="border-b border-white/[0.06] p-1">
          {([
            [1, ascLabel, ArrowUpNarrowWide],
            [-1, descLabel, ArrowDownWideNarrow],
          ] as const).map(([dir, label, Icon]) => (
            <button
              key={dir}
              type="button"
              onClick={() => {
                onSort(dir);
                onClose();
              }}
              className={cx("flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-white/[0.06]", sortDir === dir && "text-sky-300")}
            >
              <Icon className="h-3.5 w-3.5" /> {label}
            </button>
          ))}
          <button
            type="button"
            disabled={!isActive(filter)}
            onClick={() => {
              onApply(null);
              onClose();
            }}
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-white/[0.06] disabled:pointer-events-none disabled:opacity-40"
          >
            <FilterX className="h-3.5 w-3.5" /> Clear filter from &ldquo;{col}&rdquo;
          </button>
        </div>

        {kind !== "boolean" && (
          <div className="space-y-1.5 border-b border-white/[0.06] p-3">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-400">{FILTER_LABEL[kind]}</div>
            <select value={op} onChange={(e) => setOp(e.target.value as Op | "")} className={INPUT}>
              <option value="">No condition</option>
              {OPS[kind].map((o) => (
                <option key={o.op} value={o.op}>
                  {o.label}
                </option>
              ))}
            </select>
            {op && needsValue(op) && (
              <div className="flex items-center gap-1.5">
                <input type={inputType} value={a} onChange={(e) => setA(e.target.value)} placeholder="value" className={INPUT} autoFocus />
                {op === "between" && (
                  <>
                    <span className="text-ink-400">and</span>
                    <input type={inputType} value={b} onChange={(e) => setB(e.target.value)} placeholder="value" className={INPUT} />
                  </>
                )}
              </div>
            )}
          </div>
        )}

        <div className="flex min-h-0 flex-col gap-2 p-3">
          <label className="relative">
            <Search className="pointer-events-none absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-ink-400" />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search values" className={cx(INPUT, "pl-6")} />
          </label>
          <div className="min-h-0 max-h-56 overflow-auto rounded-md border border-white/[0.06] bg-ink-900/60 py-1">
            {matching.length === 0 ? (
              <div className="px-2 py-2 text-ink-400">No matching values</div>
            ) : (
              <label className="flex cursor-pointer items-center gap-2 px-2 py-1 font-medium text-ink-100 hover:bg-white/[0.04]">
                <input
                  type="checkbox"
                  className="accent-sky-400"
                  checked={checkedCount === matching.length}
                  ref={(el) => {
                    if (el) el.indeterminate = checkedCount > 0 && checkedCount < matching.length;
                  }}
                  onChange={toggleMatching}
                />
                {q ? "(Select all search results)" : "(Select all)"}
              </label>
            )}
            {listed.map((v) => (
              <label key={v.key} className="flex cursor-pointer items-center gap-2 px-2 py-1 hover:bg-white/[0.04]">
                <input type="checkbox" className="accent-sky-400" checked={selected.has(v.key)} onChange={() => toggle(v.key)} />
                <span className={cx("min-w-0 flex-1 truncate", kind === "number" && "font-mono tabular")} title={v.key}>
                  {valueLabel(v.key, kind)}
                </span>
                <span className="shrink-0 text-[10px] text-ink-400 tabular">{v.count.toLocaleString("en-IN")}</span>
              </label>
            ))}
            {matching.length > MAX_LISTED && (
              <div className="px-2 py-1.5 text-[10.5px] text-ink-400">
                Showing {MAX_LISTED} of {matching.length.toLocaleString("en-IN")} values; search to narrow the list.
              </div>
            )}
          </div>
        </div>

        <div className="flex justify-end gap-2 border-t border-white/[0.06] px-3 py-2">
          <button type="button" onClick={onClose} className="rounded-md border border-white/[0.08] px-3 py-1.5 hover:bg-white/5">
            Cancel
          </button>
          <button
            type="submit"
            disabled={!anySelected}
            className="rounded-md bg-sky-500/90 px-3 py-1.5 font-medium text-ink-950 hover:bg-sky-400 disabled:opacity-40"
          >
            OK
          </button>
        </div>
      </form>
    </Popover>
  );
}

export function ColumnsMenu({
  anchor,
  columns,
  hidden,
  initiallyHidden,
  highlight,
  onChange,
  onClose,
}: {
  anchor: DOMRect;
  columns: string[];
  hidden: Set<string>;
  initiallyHidden: string[];
  highlight?: Set<string>;
  onChange: (hidden: Set<string>) => void;
  onClose: () => void;
}) {
  const [search, setSearch] = useState("");
  const q = search.trim().toLowerCase();
  const listed = q ? columns.filter((c) => c.toLowerCase().includes(q)) : columns;
  const shownCount = columns.length - hidden.size;

  const toggle = (col: string) => {
    const next = new Set(hidden);
    if (next.has(col)) next.delete(col);
    else if (shownCount > 1) next.add(col);
    onChange(next);
  };

  return (
    <Popover anchor={anchor} width={320} onClose={onClose}>
      <div className="flex items-center justify-between gap-2 border-b border-white/[0.06] px-3 py-2">
        <span className="text-ink-100">
          {shownCount} of {columns.length} columns shown
        </span>
        <div className="flex gap-1">
          <button onClick={() => onChange(new Set())} className="rounded-md px-2 py-1 text-sky-300 hover:bg-white/[0.06]">
            Show all
          </button>
          <button onClick={() => onChange(new Set(initiallyHidden))} className="rounded-md px-2 py-1 text-ink-300 hover:bg-white/[0.06]">
            Reset
          </button>
        </div>
      </div>
      <div className="flex min-h-0 flex-col gap-2 p-3">
        <label className="relative">
          <Search className="pointer-events-none absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-ink-400" />
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Find a column" className={cx(INPUT, "pl-6")} autoFocus />
        </label>
        <div className="min-h-0 max-h-80 overflow-auto rounded-md border border-white/[0.06] bg-ink-900/60 py-1">
          {listed.map((c) => (
            <label key={c} className="flex cursor-pointer items-center gap-2 px-2 py-1 hover:bg-white/[0.04]">
              <input type="checkbox" className="accent-sky-400" checked={!hidden.has(c)} onChange={() => toggle(c)} />
              <span className={cx("min-w-0 flex-1 truncate font-mono text-[11px]", highlight?.has(c) ? "text-sky-200" : "text-ink-200")} title={c}>
                {c}
              </span>
            </label>
          ))}
          {!listed.length && <div className="px-2 py-2 text-ink-400">No matching columns</div>}
        </div>
      </div>
    </Popover>
  );
}
