/** From what is typed in the experiment form to the body of POST /experiments (#77). */

import type { Direction, ExperimentSpec, FaultKind } from "./api";

/** What the form holds. It keeps both ms and kbps, whichever kind is selected. */
export type FormValues = {
  name: string;
  kind: FaultKind;
  direction: Direction;
  ms: number;
  kbps: number;
  rate: number;
  baseline_s: number;
  inject_s: number;
  recover_s: number;
  max_p95_ms: number;
  max_error_rate: number; // 0.0–1.0
};

// What the lab's gateway needs in every POST /orders (lab/src/chaosnet_lab/gateway.py).
export const LOAD_BODY = { item_id: "42" };

/** The spec for `link`, with only the fault value that belongs to the kind. */
export function toSpec(values: FormValues, link: string): ExperimentSpec {
  throw new Error("not written yet: Tomáš, #77");
}
