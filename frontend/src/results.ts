/** Numbers the UI shows for a measured phase (#78). */

import type { PhaseSummary } from "./api";

/**
 * Share of scheduled requests that ended neither "ok" nor "degraded" (a fallback's answer,
 * ADR-010), 0.0–1.0, as `judge` counts it in backend/src/chaosnet/experiments.py. null
 * when nothing was scheduled: no requests is not the same as no errors.
 */
export function errorRate(summary: PhaseSummary): number | null {
  if (summary.scheduled === 0) {
    return null;
  }
  const answered = (summary.outcomes.ok ?? 0) + (summary.outcomes.degraded ?? 0);
  return (summary.scheduled - answered) / summary.scheduled;
}

/** Share of scheduled requests answered by a fallback (ADR-010); null as for errorRate. */
export function degradedRate(summary: PhaseSummary): number | null {
  if (summary.scheduled === 0) {
    return null;
  }
  return (summary.outcomes.degraded ?? 0) / summary.scheduled;
}
