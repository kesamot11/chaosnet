import { render, screen, within } from "@testing-library/react";
import { expect, test } from "vitest";
import { type Experiment, JAEGER } from "./api";
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
  // y counts from the top: the highest value is at y 0; the line is 94 high (120 - 20 - 6)
  expect(inject?.every((y) => y < 5)).toBe(true);
  expect(baseline?.every((y) => y > 84)).toBe(true);
  expect(recover?.every((y) => y > 84)).toBe(true);
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

test("a dot per second links to its trace in Jaeger; no trace, no dot (#173)", () => {
  const baseline = EXPERIMENT.results.baseline;
  if (baseline === undefined) throw new Error("the recording has a baseline");
  const traced: Experiment = {
    ...EXPERIMENT,
    results: {
      baseline: {
        ...baseline,
        per_second: baseline.per_second.map((p, s) => ({
          ...p,
          trace: s === 0 ? null : `trace-${s}`,
        })),
      },
    },
  };
  render(<LatencyChart experiment={traced} />);
  const p95 = screen.getByRole("img", { name: "p95 latency" });
  const links = [...p95.querySelectorAll("a")].map((a) => a.getAttribute("href"));
  expect(links).toEqual([1, 2, 3, 4].map((s) => `${JAEGER}/trace/trace-${s}`));
});

test("a record from before #173 has no trace per second, so no dots", () => {
  // the recording is such a record: its per_second entries have no `trace` key
  expect(EXPERIMENT.results.baseline?.per_second[0]).not.toHaveProperty("trace");
  render(<LatencyChart experiment={EXPERIMENT} />);
  expect(screen.getByRole("img", { name: "p95 latency" }).querySelectorAll("a")).toHaveLength(0);
});
