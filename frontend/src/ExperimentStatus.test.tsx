import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import type { Experiment, PhaseSummary } from "./api";
import { ExperimentStatus } from "./ExperimentStatus";

function measured(p50: number, p95: number, ok: number, failed = 0): PhaseSummary {
  return {
    scheduled: ok + failed,
    outcomes: failed > 0 ? { ok, timeout: failed } : { ok },
    latency_ms: { ok: null, all: { p50, p95, p99: p95, p100: p95 } },
  };
}

const BASELINE = measured(10.42, 15.07, 200);
const INJECT = measured(210.3, 230.81, 285, 15);

function experiment(fields: Partial<Experiment>): Experiment {
  return {
    id: 7,
    name: "slow inventory",
    state: "inject",
    results: {},
    verdict: null,
    reason: null,
    ...fields,
  };
}

function show(exp: Experiment, unreachable = false, onAbort = () => {}) {
  render(<ExperimentStatus experiment={exp} unreachable={unreachable} onAbort={onAbort} />);
}

function row(phase: string) {
  return screen.getByRole("row", { name: new RegExp(`^${phase}`) });
}

test("while running: the phase, what is measured so far, and Abort", () => {
  const onAbort = vi.fn();
  show(experiment({ state: "inject", results: { baseline: BASELINE } }), false, onAbort);
  expect(screen.getByText(/slow inventory/)).toBeInTheDocument();
  expect(screen.getByText(/inject \(2\/3\)/)).toBeInTheDocument();
  // p50, p95 and the error rate, one decimal each
  expect(row("baseline")).toHaveTextContent(/10\.4 ms.*15\.1 ms.*0\.0 %/);
  expect(within(row("inject")).getAllByText("-")).toHaveLength(3); // not measured yet
  expect(within(row("recover")).getAllByText("-")).toHaveLength(3);
  fireEvent.click(screen.getByRole("button", { name: "Abort" }));
  expect(onAbort).toHaveBeenCalledOnce();
});

test("completed and passed: the verdict, no Abort", () => {
  show(
    experiment({
      state: "completed",
      results: { baseline: BASELINE, inject: BASELINE, recover: BASELINE },
      verdict: { passed: true, reasons: [] },
    }),
  );
  expect(screen.getByText(/passed/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Abort" })).not.toBeInTheDocument();
});

test("completed and failed: every broken limit", () => {
  show(
    experiment({
      state: "completed",
      results: { baseline: BASELINE, inject: INJECT, recover: BASELINE },
      verdict: { passed: false, reasons: ["p95 230.8 ms > 200 ms", "error rate 5.0 % > 1.0 %"] },
    }),
  );
  expect(row("inject")).toHaveTextContent(/210\.3 ms.*230\.8 ms.*5\.0 %/);
  expect(screen.getByText(/failed/)).toBeInTheDocument();
  expect(screen.getByText("p95 230.8 ms > 200 ms")).toBeInTheDocument();
  expect(screen.getByText("error rate 5.0 % > 1.0 %")).toBeInTheDocument();
});

test("aborted: why, no Abort", () => {
  show(
    experiment({
      state: "aborted",
      results: { baseline: BASELINE },
      reason: "controller restarted during inject",
    }),
  );
  expect(screen.getByText(/aborted/)).toBeInTheDocument();
  expect(screen.getByText(/controller restarted during inject/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Abort" })).not.toBeInTheDocument();
});

test("a phase without requests says so instead of 0 %", () => {
  const empty: PhaseSummary = { scheduled: 0, outcomes: {}, latency_ms: { ok: null, all: null } };
  show(experiment({ state: "inject", results: { baseline: empty } }));
  expect(row("baseline")).toHaveTextContent("no requests");
  expect(row("baseline")).not.toHaveTextContent("%");
});

test("no answer from the controller: says so and keeps the last known state", () => {
  show(experiment({ state: "inject", results: { baseline: BASELINE } }), true);
  expect(screen.getByText(/Controller not reachable, retrying/)).toBeInTheDocument();
  expect(screen.getByText(/inject \(2\/3\)/)).toBeInTheDocument();
});
