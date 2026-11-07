import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ExperimentForm } from "./ExperimentForm";
import { recall } from "./progress";

function reply(status: number, body: unknown) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })));
}

function fillAndStart(name = "slow inventory") {
  fireEvent.change(screen.getByLabelText("Name"), { target: { value: name } });
  fireEvent.click(screen.getByRole("button", { name: "Start" }));
}

const onStarted = vi.fn();

afterEach(() => {
  onStarted.mockReset();
  vi.unstubAllGlobals();
});

test("starts the experiment on the selected link", async () => {
  reply(201, { id: 7, name: "slow inventory", state: "pending", reason: null });
  render(<ExperimentForm link="orders-inventory" onStarted={onStarted} running={false} />);
  fillAndStart();
  expect(await screen.findByText("Experiment #7 started")).toBeInTheDocument();
  expect(onStarted).toHaveBeenCalledWith(7);
  expect(recall(7, "baseline")).not.toBeNull();
  const body = JSON.parse(vi.mocked(fetch).mock.calls[0]?.[1]?.body as string);
  expect(body.fault).toEqual({
    kind: "latency",
    link: "orders-inventory",
    direction: "both",
    ms: 200,
  });
});

test("Start is blocked while waiting for the answer", async () => {
  vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {}))); // never answers
  render(<ExperimentForm link="orders-inventory" onStarted={onStarted} running={false} />);
  fillAndStart();
  expect(await screen.findByRole("button", { name: "Starting…" })).toBeDisabled();
  expect(fetch).toHaveBeenCalledTimes(1);
});

test("a refusal shows the reason and keeps what was typed", async () => {
  reply(409, { detail: "experiment 3 is already running" });
  render(<ExperimentForm link="orders-inventory" onStarted={onStarted} running={false} />);
  fillAndStart("my experiment");
  expect(await screen.findByRole("alert")).toHaveTextContent("experiment 3 is already running");
  expect(screen.getByLabelText("Name")).toHaveValue("my experiment");
  expect(onStarted).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Start" })).toBeEnabled(); // can try again
});

test("only the field of the chosen kind can be typed in", () => {
  render(<ExperimentForm link="orders-inventory" onStarted={onStarted} running={false} />);
  expect(screen.getByLabelText("Bandwidth kbps")).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Kind"), { target: { value: "bandwidth" } });
  expect(screen.getByLabelText("Latency ms")).toBeDisabled();
  expect(screen.getByLabelText("Bandwidth kbps")).toBeEnabled();
});

test("Start waits while an experiment runs, and says why (Tomáš, #209)", () => {
  const { rerender } = render(
    <ExperimentForm link="orders-inventory" onStarted={onStarted} running={true} />,
  );
  expect(screen.getByRole("button", { name: "Start" })).toBeDisabled();
  expect(screen.getByText("An experiment is running.")).toBeInTheDocument();

  rerender(<ExperimentForm link="orders-inventory" onStarted={onStarted} running={false} />);
  expect(screen.getByRole("button", { name: "Start" })).toBeEnabled();
  expect(screen.queryByText("An experiment is running.")).not.toBeInTheDocument();
});
