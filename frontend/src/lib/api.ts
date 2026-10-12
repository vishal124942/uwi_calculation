import type { Meta, TraceEvent } from "./types";

export const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export interface RunOptions {
  legalOwnerType: string;
  accountType: string;
  policyId: string;
  asOfDate: string;
  customerId: string;
  applicationId: string;
}

export type RunInput =
  | { kind: "demo"; scenario: string; options: RunOptions }
  | { kind: "upload"; files: File[]; options: RunOptions };

async function errorDetail(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    return JSON.stringify(body.detail ?? body);
  } catch {
    return `${response.status} ${response.statusText}`;
  }
}

export async function fetchMeta(signal?: AbortSignal): Promise<Meta> {
  const response = await fetch(`${API_BASE}/v1/ui/meta`, { signal });
  if (!response.ok) throw new Error(await errorDetail(response));
  return response.json();
}

function traceRequest(input: RunInput): { url: string; init: RequestInit } {
  const o = input.options;
  const params = new URLSearchParams({ legal_owner_type: o.legalOwnerType, policy_id: o.policyId });
  if (input.kind === "demo") {
    params.set("scenario", input.scenario);
    return { url: `${API_BASE}/v1/ui/trace/demo?${params}`, init: { method: "POST" } };
  }
  params.set("account_type", o.accountType);
  if (o.customerId) params.set("customer_id", o.customerId);
  if (o.applicationId) params.set("application_id", o.applicationId);
  if (o.asOfDate) params.set("as_of_date", o.asOfDate);
  const form = new FormData();
  input.files.forEach((f) => form.append("files", f, f.name));
  return { url: `${API_BASE}/v1/ui/trace?${params}`, init: { method: "POST", body: form } };
}

/** Streams the NDJSON trace, calling `onEvent` for each pipeline event as soon as it arrives. */
export async function streamTrace(
  input: RunInput,
  onEvent: (event: TraceEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const { url, init } = traceRequest(input);
  const response = await fetch(url, { ...init, signal });
  if (!response.ok || !response.body) throw new Error(await errorDetail(response));

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    let newline: number;
    while ((newline = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, newline).trim();
      buffer = buffer.slice(newline + 1);
      if (line) onEvent(JSON.parse(line) as TraceEvent);
    }
    if (done) break;
  }
  if (buffer.trim()) onEvent(JSON.parse(buffer) as TraceEvent);
}
