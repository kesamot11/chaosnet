/** Numbers the UI shows for a measured phase (#78). */

import type { PhaseSummary } from "./api";

/**
 * Share of scheduled requests that did not end "ok", 0.0–1.0, as `judge` counts it in
 * backend/src/chaosnet/experiments.py. null when nothing was scheduled: no requests is
 * not the same as no errors.
 */
export function errorRate(summary: PhaseSummary): number | null {
  if (summary.scheduled === 0) {
    return null;
  }
  return (summary.scheduled - (summary.outcomes.ok ?? 0)) / summary.scheduled;
}
