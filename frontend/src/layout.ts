import type { Topology } from "./api";

export const COLUMN_GAP = 220;
export const ROW_GAP = 100;

export type Position = { x: number; y: number };

/**
 * Tomáš (#76, plan in words first): where each service goes, read left to right like the
 * traffic. Column = the highest column of the services that call it, plus 1; a service that
 * nobody calls is in column 0. Row = its order within the column, as listed in `services`.
 * x = column × COLUMN_GAP, y = row × ROW_GAP. The topology has no cycles (checked by the API).
 */
export function layout(topology: Topology): Record<string, Position> {
  throw new Error(`layout not written yet (${topology.services.length} services)`);
}
