import type { Topology } from "./api";

export const COLUMN_GAP = 300;
export const ROW_GAP = 100;

export type Position = { x: number; y: number };

/**
 * Where each service goes (#76, plan by Tomáš), read left to right like the
 * traffic. Column = the highest column of the services that call it, plus 1; a service that
 * nobody calls is in column 0. Row = its order within the column, as listed in `services`.
 * x = column × COLUMN_GAP, y = row × ROW_GAP. The topology has no cycles (checked by the API).
 */
export function layout(topology: Topology): Record<string, Position> {
  const callers: Record<string, string[]> = {};

  for (const service of topology.services) {
    callers[service.name] = [];
  }

  for (const link of topology.links) {
    callers[link.to]?.push(link.from);
  }

  // ponytail: recomputes shared callers, exponential on many diamonds; memoize if labs grow.
  function column(name: string): number {
    const whoCalls = callers[name] ?? [];
    if (whoCalls.length === 0) {
      return 0;
    }
    const callerColumns = whoCalls.map(column);
    return Math.max(...callerColumns) + 1;
  }

  const result: Record<string, Position> = {};
  const rowsUsed: number[] = [];

  for (const service of topology.services) {
    const c = column(service.name);
    const r = rowsUsed[c] ?? 0;
    rowsUsed[c] = r + 1;
    result[service.name] = { x: c * COLUMN_GAP, y: r * ROW_GAP };
  }

  return result;
}
