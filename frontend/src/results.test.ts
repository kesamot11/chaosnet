import { expect, test } from "vitest";
import type { PhaseSummary } from "./api";
import { degradedRate, errorRate } from "./results";

function phase(scheduled: number, outcomes: Record<string, number>): PhaseSummary {
  return { scheduled, outcomes, latency_ms: { ok: null, all: null }, per_second: [] };
}

test("no errors", () => {
  expect(errorRate(phase(200, { ok: 200 }))).toBe(0);
});

test("a quarter failed", () => {
  expect(errorRate(phase(200, { ok: 150, timeout: 50 }))).toBe(0.25);
});

test("everything failed: there is no ok key at all", () => {
  expect(errorRate(phase(200, { timeout: 120, error: 80 }))).toBe(1);
});

test("dropped requests count as errors: they were scheduled and never answered", () => {
  expect(errorRate(phase(100, { ok: 90, dropped: 10 }))).toBe(0.1);
});

test("nothing scheduled: unknown, not zero", () => {
  expect(errorRate(phase(0, {}))).toBeNull();
});

test("a fallback's answer is not an error, but is counted on its own (ADR-010)", () => {
  const s = phase(200, { ok: 50, degraded: 100, timeout: 50 });
  expect(errorRate(s)).toBe(0.25);
  expect(degradedRate(s)).toBe(0.5);
});
