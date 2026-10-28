import { render, screen, within } from "@testing-library/react";
import { expect, test } from "vitest";
import type { Experiment } from "./api";
import recorded from "./fixtures/latency-200ms.json";
import { LatencyChart } from "./LatencyChart";

// Recorded from the real lab on 2026-10-28: +200 ms on orders-inventory in both
// directions, 20 req/s, 5 s per phase. p95 is ~12 ms, then ~415 ms (200 ms each way).
const EXPERIMENT = recorded as Experiment;

test("draws a recorded real experiment: one line per phase, phases marked", () => {
  render(<LatencyChart experiment={EXPERIMENT} />);
  const p95 = screen.getByRole("img", { name: "p95 latency" });
  const errors = screen.getByRole("img", { name: "error rate" });
  // every second was measured, so one line per phase: not joined across a phase border
  expect(p95.querySelectorAll("polyline")).toHaveLength(3);
  expect(errors.querySelectorAll("polyline")).toHaveLength(3);
  expect(within(p95).getByText("inject")).toBeInTheDocument();
  expect(p95.querySelectorAll("line")).toHaveLength(2); // borders before inject and recover
  expect(screen.getByText(/p95 latency \(top: 418\.7 ms\)/)).toBeInTheDocument();
});

test("the inject phase is drawn high, baseline and recover low", () => {
  render(<LatencyChart experiment={EXPERIMENT} />);
  const [baseline, inject, recover] = [
    ...screen.getByRole("img", { name: "p95 latency" }).querySelectorAll("polyline"),
  ].map((line) =>
    (line.getAttribute("points") ?? "").split(" ").map((p) => Number(p.split(",")[1])),
  );
  // y counts from the top: the highest value is at y 0, the chart is 120 high
  expect(inject?.every((y) => y < 5)).toBe(true);
  expect(baseline?.every((y) => y > 110)).toBe(true);
  expect(recover?.every((y) => y > 110)).toBe(true);
});

test("a phase not measured yet leaves its part of the chart empty", () => {
  const running: Experiment = {
    ...EXPERIMENT,
    state: "inject",
    results: { baseline: EXPERIMENT.results.baseline },
  };
  render(<LatencyChart experiment={running} />);
  const line = screen.getByRole("img", { name: "p95 latency" }).querySelector("polyline");
  expect(line?.getAttribute("points")?.split(" ")).toHaveLength(5); // the 5 baseline seconds
});
