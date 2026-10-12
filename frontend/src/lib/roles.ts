const ROLE_COLORS: Record<string, string> = {
  C01: "#34d399", C02: "#2dd4bf", C03: "#a3e635", C04: "#94a3b8", C05: "#fb923c", C06: "#fbbf24",
  C07: "#facc15", C08: "#22d3ee", C09: "#38bdf8", C10: "#60a5fa", C11: "#f472b6", C12: "#a78bfa",
  C13: "#64748b",
  D01: "#f87171", D02: "#fb7185", D03: "#f97316", D04: "#fbbf24", D05: "#eab308", D06: "#e879f9",
  D07: "#c084fc", D08: "#fb923c", D09: "#f59e0b", D10: "#38bdf8", D11: "#22d3ee", D12: "#f472b6",
  D13: "#ec4899", D14: "#94a3b8", D15: "#67e8f9", D16: "#a3e635", D17: "#a78bfa", D18: "#cbd5e1",
  D19: "#64748b",
};

export function roleColor(code: string | null | undefined): string {
  return (code && ROLE_COLORS[code]) || "#64748b";
}

export const OPERATING_CREDIT_ROLES = ["C01", "C02", "C03"];
export const CORE_DEBIT_ROLES = ["D01", "D02", "D03", "D04", "D05", "D06", "D07", "D16", "D18"];

export function roleLabel(roles: Record<string, string> | undefined, code: string | null | undefined): string {
  if (!code) return "—";
  return roles?.[code] ?? code;
}
