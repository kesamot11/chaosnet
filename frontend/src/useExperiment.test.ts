import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { State } from "./api";
import { POLL_MS, RETRY_MS, useExperiment } from "./useExperiment";

function record(state: State) {
  return { id: 7, name: "slow inventory", state, results: {}, verdict: null, reason: null };
}

/** fetch that answers with these states, one per call, then keeps answering the last. */
function controllerSays(...answers: (State | "down")[]) {
  const fetch = vi.fn();
  for (const a of answers) {
    if (a === "down") fetch.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    else fetch.mockImplementationOnce(async () => new Response(JSON.stringify(record(a))));
  }
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

async function wait(ms: number) {
  await act(() => vi.advanceTimersByTimeAsync(ms));
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

test("polls every second and stops at an end state", async () => {
  const fetch = controllerSays("baseline", "inject", "completed");
  const { result } = renderHook(() => useExperiment(7));
  await wait(0);
  expect(result.current.experiment?.state).toBe("baseline");
  await wait(POLL_MS);
  expect(result.current.experiment?.state).toBe("inject");
  await wait(POLL_MS);
  expect(result.current.experiment?.state).toBe("completed");
  await wait(10 * POLL_MS);
  expect(fetch).toHaveBeenCalledTimes(3);
  expect(fetch).toHaveBeenCalledWith("/api/experiments/7", expect.anything());
});

test("no answer: says so, tries again after 30 s, then every second again", async () => {
  const fetch = controllerSays("inject", "down", "aborted");
  const { result } = renderHook(() => useExperiment(7));
  await wait(0);
  await wait(POLL_MS);
  expect(result.current.unreachable).toBe(true);
  expect(result.current.experiment?.state).toBe("inject"); // the last known state stays
  await wait(RETRY_MS - 1);
  expect(fetch).toHaveBeenCalledTimes(2);
  await wait(1);
  expect(result.current.unreachable).toBe(false);
  expect(result.current.experiment?.state).toBe("aborted"); // what reconcile wrote
});

test("goes back to every second once the controller answers", async () => {
  const fetch = controllerSays("down", "inject", "inject");
  renderHook(() => useExperiment(7));
  await wait(0);
  await wait(RETRY_MS);
  await wait(POLL_MS);
  expect(fetch).toHaveBeenCalledTimes(3);
});

test("no polling left after the view is closed", async () => {
  const fetch = controllerSays("inject", "inject", "inject");
  const { unmount } = renderHook(() => useExperiment(7));
  await wait(0);
  unmount();
  await wait(10 * POLL_MS);
  expect(fetch).toHaveBeenCalledTimes(1);
});

test("nothing to poll without an experiment", async () => {
  const fetch = controllerSays();
  const { result } = renderHook(() => useExperiment(null));
  await wait(10 * POLL_MS);
  expect(fetch).not.toHaveBeenCalled();
  expect(result.current.experiment).toBeNull();
});
