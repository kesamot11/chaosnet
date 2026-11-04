import type { State } from "./api";

export type Progress =
  | { kind: "unknown"; total_s: number }
  | { kind: "running"; elapsed_s: number; total_s: number }
  | { kind: "waiting" };

export function phaseProgress(
  started_ms: number | null,
  total_s: number,
  now_ms: number,
): Progress {
  if (started_ms == null) {
    return { kind: "unknown", total_s };
  }
  const elapsed_s = (now_ms - started_ms) / 1000;
  if (elapsed_s <= total_s) {
    return { kind: "running", elapsed_s, total_s };
  }
  return { kind: "waiting" };
}

function key(id: number, phase: State): string {
  return `chaosnet:${id}:${phase}`;
}

export function remember(id: number, phase: State, ms: number): void {
  try {
    localStorage.setItem(key(id, phase), String(ms));
  } catch {
    // not saved: recall returns null later, so the user sees the "page wasn't open" message
  }
}

export function recall(id: number, phase: State): number | null {
  try {
    const saved = localStorage.getItem(key(id, phase));
    if (saved === null) {
      return null;
    }
    return Number(saved);
  } catch {
    return null;
  }
}
