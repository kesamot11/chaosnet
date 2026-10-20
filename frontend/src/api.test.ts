import { afterEach, expect, test, vi } from "vitest";
import { type ExperimentSpec, startExperiment } from "./api";

const SPEC: ExperimentSpec = {
  name: "slow inventory",
  fault: { kind: "latency", link: "orders-inventory", direction: "both", ms: 200 },
  load: { rate: 20, body: {} },
  phases_s: { baseline: 10, inject: 15, recover: 10 },
  hypothesis: { max_p95_ms: 500, max_error_rate: 0.01 },
};

function reply(status: number, body: unknown) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status })));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

test("posts the spec and returns the new experiment", async () => {
  reply(201, { id: 7, name: "slow inventory", state: "pending", reason: null });
  expect(await startExperiment(SPEC)).toEqual({
    ok: true,
    experiment: { id: 7, name: "slow inventory", state: "pending", reason: null },
  });
  expect(fetch).toHaveBeenCalledWith(
    "/api/experiments",
    expect.objectContaining({ method: "POST", body: JSON.stringify(SPEC) }),
  );
});

test("409: the controller's reason", async () => {
  reply(409, { detail: "experiment 3 is already running" });
  expect(await startExperiment(SPEC)).toEqual({
    ok: false,
    reason: "experiment 3 is already running",
  });
});

test("422 from validation: each field and what is wrong with it", async () => {
  reply(422, {
    detail: [
      { loc: ["body", "phases_s", "inject"], msg: "Input should be greater than 0" },
      { loc: ["body", "load", "rate"], msg: "Input should be greater than 0" },
    ],
  });
  expect(await startExperiment(SPEC)).toEqual({
    ok: false,
    reason:
      "phases_s.inject: Input should be greater than 0; load.rate: Input should be greater than 0",
  });
});

test("an error without a JSON body, as from the dev proxy", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 502 })));
  expect(await startExperiment(SPEC)).toEqual({ ok: false, reason: "Controller error: HTTP 502" });
});

test("no answer at all", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
  expect(await startExperiment(SPEC)).toEqual({
    ok: false,
    reason: "Controller not reachable: Failed to fetch",
  });
});
