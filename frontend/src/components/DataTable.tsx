"use client";

import { useVirtualizer } from "@tanstack/react-virtual";
import { ArrowDown, ArrowUp, ChevronDown, Columns3, Download, Filter, Maximize2, Minimize2, Search, X } from "lucide-react";
import { type ReactNode, useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { cellText } from "@/lib/format";
import { roleColor } from "@/lib/roles";
import { applyFilters, type ColumnFilter, columnKinds, describeFilter, distinctValues, type Filters, isActive } from "@/lib/tableFilter";
import type { Cell, Row } from "@/lib/types";
import { ColumnsMenu, FilterMenu } from "./TableMenus";
import { cx } from "./ui";

const ROW_HEIGHT = 34;

function columnWidth(col: string): number {
  if (/narration|description|meaning|note|reason$/.test(col)) return 360;
  if (/probabilities$/.test(col)) return 260;
  if (/transaction_id|_txn$|txn_id|cluster_id|edge_id/.test(col)) return 210;
  if (/name_tokens|active_months|rules_applied|adjustments_applied|evidence|triggers|warnings|hard_stop/.test(col)) return 220;
  if (/date|^day$|^start$|^end$|first_seen/.test(col)) return 124;
  return Math.min(236, Math.max(120, col.length * 7.2 + 44));
}

function compare(a: Cell | undefined, b: Cell | undefined): number {
  if (a === b) return 0;
  if (a === null || a === undefined) return 1;
  if (b === null || b === undefined) return -1;
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b));
}

function defaultCell(col: string, v: Cell | undefined): ReactNode {
  if (v === null || v === undefined || v === "") return <span className="text-ink-500">—</span>;
  if (typeof v === "boolean") return v ? <span className="text-emerald-300">yes</span> : <span className="text-ink-400">no</span>;
  if (col === "direction") return <span className={v === "CREDIT" ? "text-emerald-300" : "text-rose-300"}>{String(v)}</span>;
  if (typeof v === "string" && /_role$/.test(col) && /^[CD]\d{2}$/.test(v)) {
    return (
      <span className="rounded px-1.5 py-0.5 font-mono text-[11px] font-semibold" style={{ color: roleColor(v), background: `${roleColor(v)}1f` }}>
        {v}
      </span>
    );
  }
  return cellText(v);
}

function toCsv(columns: string[], rows: Row[]): string {
  const esc = (v: Cell | undefined) => {
    const s = v === null || v === undefined ? "" : typeof v === "object" ? JSON.stringify(v) : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [columns.join(","), ...rows.map((r) => columns.map((c) => esc(r[c])).join(","))].join("\n");
}

const TOOL_BUTTON = "inline-flex items-center gap-1.5 rounded-lg border border-white/[0.08] px-2.5 py-1.5 text-xs text-ink-200 transition hover:bg-white/5";

export interface DataTableProps {
  columns: string[];
  rows: Row[];
  height?: number;
  highlight?: Set<string>;
  onRowClick?: (row: Row) => void;
  selectedKey?: string | null;
  rowKey?: string;
  renderCell?: (col: string, value: Cell | undefined, row: Row) => ReactNode | undefined;
  toolbar?: ReactNode;
  downloadName?: string;
  searchPlaceholder?: string;
  /** Columns listed in the Columns menu but hidden until the user shows them. */
  hiddenColumns?: string[];
  /** Heading of the full panel view. */
  title?: ReactNode;
}

export default function DataTable({
  columns,
  rows,
  height = 520,
  highlight,
  onRowClick,
  selectedKey,
  rowKey = "transaction_id",
  renderCell,
  toolbar,
  downloadName,
  searchPlaceholder = "Search all columns…",
  hiddenColumns,
  title,
}: DataTableProps) {
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const [sort, setSort] = useState<{ col: string; dir: 1 | -1 } | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(() => new Set(hiddenColumns ?? []));
  const [filters, setFilters] = useState<Filters>({});
  const [menu, setMenu] = useState<{ col: string; anchor: DOMRect } | null>(null);
  const [columnsAnchor, setColumnsAnchor] = useState<DOMRect | null>(null);
  const [expanded, setExpanded] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const shown = useMemo(() => columns.filter((c) => !hidden.has(c)), [columns, hidden]);
  const widths = useMemo(() => shown.map(columnWidth), [shown]);
  const totalWidth = widths.reduce((a, b) => a + b, 0);
  const kinds = useMemo(() => columnKinds(rows, [...new Set([...columns, ...Object.keys(filters)])]), [rows, columns, filters]);

  const visible = useMemo(() => {
    const q = deferredQuery.trim().toLowerCase();
    let out = applyFilters(rows, filters, kinds);
    if (q) {
      out = out.filter((r) =>
        shown.some((c) => {
          const v = r[c];
          return v !== null && v !== undefined && String(typeof v === "object" ? JSON.stringify(v) : v).toLowerCase().includes(q);
        }),
      );
    }
    if (sort) out = [...out].sort((a, b) => compare(a[sort.col], b[sort.col]) * sort.dir);
    return out;
  }, [rows, shown, deferredQuery, sort, filters, kinds]);

  const menuRows = useMemo(() => (menu ? applyFilters(rows, filters, kinds, menu.col) : []), [menu, rows, filters, kinds]);
  const activeFilters = Object.entries(filters).filter((e): e is [string, ColumnFilter] => isActive(e[1]));

  // eslint-disable-next-line react-hooks/incompatible-library -- TanStack Virtual is used as documented
  const virtualizer = useVirtualizer({
    count: visible.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 12,
  });

  useEffect(() => {
    if (!expanded) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !document.querySelector("[data-txn-drawer]")) setExpanded(false);
    };
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = overflow;
      window.removeEventListener("keydown", onKey);
    };
  }, [expanded]);

  const closeMenu = useCallback(() => setMenu(null), []);
  const closeColumns = useCallback(() => setColumnsAnchor(null), []);

  const toggleSort = (col: string) =>
    setSort((s) => (s?.col !== col ? { col, dir: -1 } : s.dir === -1 ? { col, dir: 1 } : null));

  const setFilter = (col: string, f: ColumnFilter | null) =>
    setFilters((prev) => {
      const next = { ...prev };
      if (f) next[col] = f;
      else delete next[col];
      return next;
    });

  const download = () => {
    const blob = new Blob([toCsv(shown, visible)], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${downloadName ?? "table"}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const content = (
    <div className={cx("flex flex-col gap-3", expanded && "min-h-0 flex-1")}>
      <div className="flex flex-wrap items-center gap-2">
        <label className="relative min-w-56 flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-400" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={searchPlaceholder}
            className="w-full rounded-lg border border-white/[0.08] bg-ink-850 py-1.5 pl-8 pr-3 text-xs text-ink-100 placeholder:text-ink-400 focus:border-sky-400/50 focus:outline-none"
          />
        </label>
        {toolbar}
        <span className="text-xs text-ink-400 tabular">
          {visible.length.toLocaleString("en-IN")} of {rows.length.toLocaleString("en-IN")} rows · {shown.length}
          {shown.length < columns.length && ` of ${columns.length}`} columns
        </span>
        <button
          data-menu-anchor
          onClick={(e) => {
            const rect = e.currentTarget.getBoundingClientRect();
            setColumnsAnchor((a) => (a ? null : rect));
          }}
          className={cx(TOOL_BUTTON, columnsAnchor && "bg-white/5")}
        >
          <Columns3 className="h-3.5 w-3.5" /> Columns
        </button>
        <button onClick={download} className={TOOL_BUTTON} title="Download the filtered rows and shown columns">
          <Download className="h-3.5 w-3.5" /> CSV
        </button>
        <button onClick={() => setExpanded((x) => !x)} className={TOOL_BUTTON} title={expanded ? "Back to the page (Esc)" : "Open the table in a full panel"}>
          {expanded ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
          {expanded ? "Exit full panel" : "Full panel"}
        </button>
      </div>

      {(activeFilters.length > 0 || sort) && (
        <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
          {activeFilters.map(([col, f]) => (
            <span key={col} className="inline-flex max-w-md items-center gap-1 rounded-md border border-sky-400/25 bg-sky-400/[0.08] py-0.5 pl-2 pr-0.5 text-sky-100">
              <Filter className="h-3 w-3 shrink-0 text-sky-300" />
              <button
                data-menu-anchor
                className="truncate"
                onClick={(e) => {
                  const rect = e.currentTarget.getBoundingClientRect();
                  setMenu((m) => (m?.col === col ? null : { col, anchor: rect }));
                }}
              >
                <span className="font-mono">{col}</span>
                <span className="text-sky-200/70">: {describeFilter(f, kinds[col] ?? "text", distinctValues(rows, col, kinds[col] ?? "text").length)}</span>
              </button>
              <button onClick={() => setFilter(col, null)} title="Remove this filter" className="rounded p-0.5 hover:bg-white/10">
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
          {sort && (
            <span className="inline-flex items-center gap-1 rounded-md border border-white/[0.08] py-0.5 pl-2 pr-0.5 text-ink-200">
              {sort.dir === 1 ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />}
              sorted by <span className="font-mono">{sort.col}</span>
              <button onClick={() => setSort(null)} title="Remove sort" className="rounded p-0.5 hover:bg-white/10">
                <X className="h-3 w-3" />
              </button>
            </span>
          )}
          {activeFilters.length > 1 && (
            <button onClick={() => setFilters({})} className="rounded-md px-2 py-0.5 text-ink-300 hover:bg-white/5 hover:text-ink-100">
              Clear all filters
            </button>
          )}
        </div>
      )}

      <div
        ref={scrollRef}
        className={cx("overflow-auto rounded-xl border border-white/[0.07] bg-ink-900", expanded && "min-h-0 flex-1")}
        style={expanded ? undefined : { height }}
      >
        <div style={{ width: totalWidth, minWidth: "100%" }}>
          <div className="sticky top-0 z-10 flex border-b border-white/10 bg-ink-800/95 backdrop-blur">
            {shown.map((c, i) => {
              const filtered = isActive(filters[c]);
              const open = menu?.col === c;
              return (
                <div
                  key={c}
                  style={{ width: widths[i] }}
                  className={cx("group flex shrink-0 items-center", highlight?.has(c) ? "bg-sky-400/[0.08] text-sky-200" : "text-ink-300")}
                >
                  <button
                    onClick={() => toggleSort(c)}
                    title={`${c} (click to sort)`}
                    className="flex min-w-0 flex-1 items-center gap-1 py-2 pl-3 text-left text-[11px] font-semibold tracking-wide"
                  >
                    <span className="truncate">{c}</span>
                    {sort?.col === c && (sort.dir === -1 ? <ArrowDown className="h-3 w-3 shrink-0" /> : <ArrowUp className="h-3 w-3 shrink-0" />)}
                  </button>
                  <button
                    data-menu-anchor
                    title={filtered ? `Filtered: ${c}` : `Filter ${c}`}
                    onClick={(e) => {
                      const rect = e.currentTarget.getBoundingClientRect();
                      setMenu((m) => (m?.col === c ? null : { col: c, anchor: rect }));
                    }}
                    className={cx(
                      "mr-1.5 shrink-0 rounded border p-0.5 transition",
                      filtered
                        ? "border-sky-400/50 bg-sky-400/20 text-sky-200"
                        : open
                          ? "border-white/20 bg-white/10 text-ink-100"
                          : "border-white/10 text-ink-400 hover:border-white/20 hover:bg-white/10 hover:text-ink-100",
                    )}
                  >
                    {filtered ? <Filter className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                  </button>
                </div>
              );
            })}
          </div>
          {visible.length === 0 && (
            <div className="px-4 py-10 text-center text-xs text-ink-400">
              No rows match{activeFilters.length ? " the column filters" : ""}
              {deferredQuery.trim() ? " and search" : ""}.
            </div>
          )}
          <div className="relative" style={{ height: virtualizer.getTotalSize() }}>
            {virtualizer.getVirtualItems().map((item) => {
              const row = visible[item.index];
              const key = row[rowKey];
              const selected = selectedKey != null && key === selectedKey;
              return (
                <div
                  key={item.key}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  className={cx(
                    "absolute left-0 flex w-full border-b border-white/[0.04] text-xs",
                    onRowClick && "cursor-pointer hover:bg-white/[0.04]",
                    selected ? "bg-sky-400/10" : item.index % 2 ? "bg-white/[0.012]" : "",
                  )}
                  style={{ height: ROW_HEIGHT, transform: `translateY(${item.start}px)` }}
                >
                  {shown.map((c, i) => {
                    const v = row[c];
                    const custom = renderCell?.(c, v, row);
                    return (
                      <div
                        key={c}
                        title={v === null || v === undefined ? undefined : cellText(v)}
                        style={{ width: widths[i] }}
                        className={cx(
                          "flex shrink-0 items-center truncate px-3 text-ink-200",
                          typeof v === "number" && "justify-end font-mono tabular",
                          highlight?.has(c) && "bg-sky-400/[0.04]",
                        )}
                      >
                        <span className="truncate">{custom !== undefined ? custom : defaultCell(c, v)}</span>
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {menu && (
        <FilterMenu
          key={menu.col}
          col={menu.col}
          kind={kinds[menu.col] ?? "text"}
          anchor={menu.anchor}
          rows={menuRows}
          filter={filters[menu.col]}
          sortDir={sort?.col === menu.col ? sort.dir : null}
          onSort={(dir) => setSort({ col: menu.col, dir })}
          onApply={(f) => setFilter(menu.col, f)}
          onClose={closeMenu}
        />
      )}
      {columnsAnchor && (
        <ColumnsMenu
          anchor={columnsAnchor}
          columns={columns}
          hidden={hidden}
          initiallyHidden={hiddenColumns ?? []}
          highlight={highlight}
          onChange={setHidden}
          onClose={closeColumns}
        />
      )}
    </div>
  );

  if (!expanded) return content;

  return (
    <>
      <div
        style={{ height }}
        className="grid place-items-center rounded-xl border border-dashed border-white/10 text-xs text-ink-400"
      >
        <button onClick={() => setExpanded(false)} className={TOOL_BUTTON}>
          <Minimize2 className="h-3.5 w-3.5" /> The table is open in the full panel; bring it back here
        </button>
      </div>
      {createPortal(
        <div role="dialog" aria-modal="true" className="fixed inset-0 z-30 flex flex-col gap-3 bg-ink-950/[0.97] p-5 backdrop-blur-sm">
          <div className="flex items-center justify-between gap-4">
            <div className="min-w-0 truncate text-sm font-semibold text-ink-100">{title ?? downloadName ?? "Table"}</div>
            <button onClick={() => setExpanded(false)} title="Close (Esc)" className="rounded-lg p-1.5 text-ink-300 hover:bg-white/10 hover:text-ink-100">
              <X className="h-4 w-4" />
            </button>
          </div>
          {content}
        </div>,
        document.body,
      )}
    </>
  );
}
