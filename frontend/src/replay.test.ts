import { expect, test } from "vitest";
import type { Experiment } from "./api";
import recorded from "./fixtures/latency-200ms.json";
import { replayed, topologyOf } from "./replay";

const run = recorded as unknown as Experiment; // a real run: 5 s per phase, completed

test("a replay shows a phase's results only when the phase has ended, like a real run", () => {
  expect(replayed(run, 0)).toMatchObject({ state: "baseline", results: {}, verdict: null });
  const inject = replayed(run, 7);
  expect(inject.state).toBe("inject");
  expect(Object.keys(inject.results)).toEqual(["baseline"]);
  expect(replayed(run, 12).state).toBe("recover");
  expect(Object.keys(replayed(run, 12).results)).toEqual(["baseline", "inject"]);
  expect(replayed(run, 15)).toBe(run); // the end: the record as it is, verdict and all
});

test("a replay changes no number: a phase it shows is the recorded one", () => {
  expect(replayed(run, 12).results.inject).toBe(run.results.inject);
});

test("the lab of a run is built from the links it recorded", () => {
  const withLinks = {
    ...run,
    topology: {
      links: [
        { from: "gateway", to: "orders", timeout_s: 2, max_retries: 1, backoff_s: 0 },
        { from: "orders", to: "inventory", timeout_s: 0.5, max_retries: 2, backoff_s: 0 },
      ],
    },
  } as unknown as Experiment;
  const lab = topologyOf(withLinks);
  expect(lab.services.map((s) => s.name)).toEqual(["gateway", "orders", "inventory"]);
  expect(lab.links.map((l) => l.name)).toEqual(["gateway-orders", "orders-inventory"]);
});

test("a replay shows only the alarms raised so far (#257)", () => {
  const alarms = [
    { at_s: 1, link: null },
    { at_s: 6.2, link: "orders-inventory" },
  ];
  const withAlarms = { ...run, alarms };
  expect(replayed(withAlarms, 3).alarms).toEqual([alarms[0]]);
  expect(replayed(withAlarms, 7).alarms).toEqual(alarms);
});
