import { useState } from "react";
import type { Severity } from "./api/stream";

export const SEVERITY: Record<Severity, { label: string; cls: string }> = {
  safety_critical: { label: "Safety-critical", cls: "bg-sev-safety" },
  needs_service: { label: "Needs service", cls: "bg-sev-service" },
  needs_adjustment: { label: "Needs adjustment", cls: "bg-sev-adjust" },
  cosmetic: { label: "Cosmetic", cls: "bg-sev-cosmetic" },
  no_action_needed: { label: "No action needed", cls: "bg-sev-none" },
};

export const nice = (v: string) => v.replace(/_/g, " ");
export const money = (cents: number) => `$${(cents / 100).toFixed(2)}`;

export function SeverityBadge({ severity }: { severity: string }) {
  const s = SEVERITY[severity as Severity];
  return (
    <span className={`inline-block px-2 py-0.5 rounded-sm text-xs font-bold text-white ${s?.cls ?? "bg-line"}`}>
      {s?.label ?? nice(severity)}
    </span>
  );
}

const STATUS: Record<string, { label: string; cls: string }> = {
  awaiting_review: { label: "Awaiting review", cls: "border-warn text-warn" },
  approved: { label: "Approved", cls: "border-good text-good" },
  rejected: { label: "Rejected", cls: "border-sev-safety text-sev-safety" },
  declined: { label: "Declined by customer", cls: "border-muted text-muted" },
  completed: { label: "Completed", cls: "border-good text-good" },
  draft: { label: "Draft", cls: "border-muted text-muted" },
};

export function StatusBadge({ status }: { status: string }) {
  const s = STATUS[status] ?? { label: nice(status), cls: "border-muted text-muted" };
  return <span className={`inline-block px-2 py-0.5 rounded-sm text-xs font-semibold border ${s.cls}`}>{s.label}</span>;
}

export const field = "border border-line rounded-sm px-2 py-1";
export const primary = "bg-accent text-header font-semibold px-4 py-1.5 rounded-sm disabled:opacity-40";
export const secondary = "border border-line font-semibold px-4 py-1.5 rounded-sm hover:border-muted disabled:opacity-40";

/** A name remembered in this browser, so the mechanic types it once. */
export function useRememberedName(key: string): [string, (v: string) => void] {
  const read = () => {
    try { return localStorage.getItem(key) ?? ""; } catch { return ""; }
  };
  const [name, setName] = useState(read);
  const set = (v: string) => {
    setName(v);
    try { localStorage.setItem(key, v); } catch { /* private mode: it just isn't remembered */ }
  };
  return [name, set];
}

/** The messages in an API error body: a string, a list of problems, or validation details. */
export function problemsFrom(error: unknown): string[] {
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  if (typeof detail === "string") return [detail];
  if (Array.isArray(detail)) return detail.map((d) => (d as { msg?: string }).msg ?? JSON.stringify(d));
  if (detail && typeof detail === "object" && "problems" in detail) return (detail as { problems: string[] }).problems;
  return ["Something went wrong."];
}
