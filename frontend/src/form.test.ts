import { describe, expect, it } from "vitest";
import { type FormValues, LOAD_BODY, toSpec } from "./form";

const values: FormValues = {
  name: "slow inventory",
  kind: "latency",
  direction: "both",
  ms: 200,
  kbps: 50,
  rate: 20,
  baseline_s: 10,
  inject_s: 15,
  recover_s: 10,
  max_p95_ms: 500,
  max_error_rate: 0.01,
};

describe("toSpec", () => {
  it("builds the whole spec for the selected link", () => {
    expect(toSpec(values, "orders-inventory")).toEqual({
      name: "slow inventory",
      fault: { kind: "latency", link: "orders-inventory", direction: "both", ms: 200 },
      load: { rate: 20, body: LOAD_BODY },
      phases_s: { baseline: 10, inject: 15, recover: 10 },
      hypothesis: { max_p95_ms: 500, max_error_rate: 0.01 },
    });
  });

  it("sends kbps and not the ms left over from latency", () => {
    const fault = toSpec({ ...values, kind: "bandwidth" }, "orders-inventory").fault;
    expect(fault).toEqual({
      kind: "bandwidth",
      link: "orders-inventory",
      direction: "both",
      kbps: 50,
    });
  });

  it("sends neither ms nor kbps for a reset", () => {
    const fault = toSpec({ ...values, kind: "reset_peer" }, "gateway-orders").fault;
    expect(fault).toEqual({ kind: "reset_peer", link: "gateway-orders", direction: "both" });
  });

  it("passes the direction through", () => {
    expect(toSpec({ ...values, direction: "response" }, "gateway-orders").fault.direction).toBe(
      "response",
    );
  });
});
