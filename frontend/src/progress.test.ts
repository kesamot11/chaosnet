import { expect, test } from "vitest";
import { phaseProgress } from "./progress";

test("the start is unknown: no bar, only the phase length", () => {
  expect(phaseProgress(null, 15, 9000)).toEqual({ kind: "unknown", total_s: 15 });
});

test("experiment is running", () => {
  expect(phaseProgress(0, 15, 9000)).toEqual({ kind: "running", elapsed_s: 9, total_s: 15 });
});

test("experiment is running edge case", () => {
  expect(phaseProgress(0, 15, 15000)).toEqual({ kind: "running", elapsed_s: 15, total_s: 15 });
});

test("experiment is waiting", () => {
  expect(phaseProgress(0, 15, 16000)).toEqual({ kind: "waiting" });
});
