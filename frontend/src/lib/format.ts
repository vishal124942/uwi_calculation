import type { Cell } from "./types";

const inrFormatters = new Map<number, Intl.NumberFormat>();

function inrFormat(digits: number): Intl.NumberFormat {
  let f = inrFormatters.get(digits);
  if (!f) {
    f = new Intl.NumberFormat("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
    inrFormatters.set(digits, f);
  }
  return f;
}

export function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

export function str(v: unknown): string {
  return v === null || v === undefined ? "" : String(v);
}

export function inr(v: unknown, digits = 0): string {
  const n = num(v);
  if (n === null) return "—";
  return `${n < 0 ? "−" : ""}₹${inrFormat(digits).format(Math.abs(n))}`;
}

/** Indian short scale: K, L (lakh), Cr (crore). */
export function inrShort(v: unknown): string {
  const n = num(v);
  if (n === null) return "—";
  const a = Math.abs(n);
  const sign = n < 0 ? "−" : "";
  if (a >= 1e7) return `${sign}₹${(a / 1e7).toFixed(2)} Cr`;
  if (a >= 1e5) return `${sign}₹${(a / 1e5).toFixed(2)} L`;
  if (a >= 1e3) return `${sign}₹${(a / 1e3).toFixed(1)} K`;
  return `${sign}₹${a.toFixed(0)}`;
}

export function pct(v: unknown, digits = 1): string {
  const n = num(v);
  return n === null ? "—" : `${(n * 100).toFixed(digits)}%`;
}

export function fixed(v: unknown, digits = 2): string {
  const n = num(v);
  if (n === null) return "—";
  return inrFormat(digits).format(n);
}

export function smartNumber(n: number): string {
  if (Number.isInteger(n)) return inrFormat(0).format(n);
  const a = Math.abs(n);
  if (a >= 100) return inrFormat(2).format(n);
  if (a >= 1) return n.toFixed(3);
  return n.toFixed(4);
}

export function cellText(v: Cell | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "number") return smartNumber(v);
  if (Array.isArray(v)) return v.length ? v.map((x) => cellText(x)).join(", ") : "—";
  if (typeof v === "object") return JSON.stringify(v);
  return v;
}

/** "BAL01_AverageDailyBalance" -> { code: "BAL01", label: "Average daily balance" }. */
export function featureName(key: string): { code: string | null; label: string } {
  const m = key.match(/^([A-Z]{1,4}\d{2,3})_(.+)$/);
  const raw = m ? m[2] : key;
  const spaced = raw
    .replace(/_/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/([A-Z]+)([A-Z][a-z])/g, "$1 $2")
    .replace(/(\d+)([a-z])/g, "$1 $2")
    .trim();
  const label = spaced.charAt(0).toUpperCase() + spaced.slice(1);
  return { code: m ? m[1] : null, label };
}

export function ms(v: number | undefined): string {
  if (v === undefined) return "";
  return v >= 1000 ? `${(v / 1000).toFixed(2)} s` : `${v.toFixed(0)} ms`;
}

export function shortId(id: string, n = 8): string {
  return id.length > n ? `${id.slice(0, n)}…` : id;
}
