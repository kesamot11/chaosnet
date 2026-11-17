import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { recall } from "./progress";
import { ReplayForm } from "./ReplayForm";

const RUNS = [
  { id: 41, link: "orders-inventory", name: "Retries", about: "Three retries hide a slow callee." },
  { id: 42, link: "orders-inventory", name: "Breaker", about: "The breaker opens." },
];

test("replays the chosen run, the first one unless another is picked", () => {
  const onStarted = vi.fn();
  render(<ReplayForm link="orders-inventory" runs={RUNS} onStarted={onStarted} running={false} />);
  fireEvent.click(screen.getByLabelText(/Breaker/));
  fireEvent.click(screen.getByRole("button", { name: "Start" }));
  expect(onStarted).toHaveBeenCalledWith(42);
  expect(recall(42, "baseline")).not.toBeNull(); // the progress bar starts now
});

test("Start waits while a replay runs, and says why", () => {
  render(<ReplayForm link="orders-inventory" runs={RUNS} onStarted={() => {}} running />);
  expect(screen.getByRole("button", { name: "Start" })).toBeDisabled();
  expect(screen.getByText("A replay is running.")).toBeInTheDocument();
});
