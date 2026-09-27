const MS_PER_SECOND = 1000;
const PERCENT = 100;

export const TERMINAL_STATUSES = new Set(["RESOLVED", "REMEDIATION_FAILED", "VERIFICATION_INCONCLUSIVE", "REJECTED", "ERROR"]);

export function formatLatency(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "n/a";
  return seconds >= 1 ? `${seconds.toFixed(1)} s` : `${Math.round(seconds * MS_PER_SECOND)} ms`;
}

export function formatPercent(ratio: number | null | undefined): string {
  if (ratio === null || ratio === undefined) return "n/a";
  return `${Math.round(ratio * PERCENT)}%`;
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function humanize(value: string | null | undefined): string {
  return value ? value.replace(/_/g, " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase()) : "—";
}

export type Tone = "good" | "bad" | "warn" | "wait" | "neutral";

export function statusTone(status: string): Tone {
  if (status === "RESOLVED") return "good";
  if (["REMEDIATION_FAILED", "ERROR"].includes(status)) return "bad";
  if (["PENDING_APPROVAL", "AWAITING_MANUAL_EXECUTION"].includes(status)) return "warn";
  if (TERMINAL_STATUSES.has(status)) return "neutral";
  return "wait";
}

export function riskTone(risk: string | null | undefined): Tone {
  return risk === "LOW" ? "good" : risk === "HIGH" ? "bad" : risk === "MEDIUM" ? "warn" : "neutral";
}
