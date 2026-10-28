import { describe, expect, it } from "vitest";
import type { Experiment, SecondSummary } from "./api";
import { segments, timeline, toPoints } from "./chart";

describe("segments", () => {
  it("scales seconds to x and values to y, with 0 at the bottom", () => {
    expect(segments([0, 100, 200, 400], 400, 300, 200)).toEqual([
      [
        { x: 0, y: 200 },
        { x: 100, y: 150 },
        { x: 200, y: 100 },
        { x: 300, y: 0 },
      ],
    ]);
  });

  it("a null breaks the line", () => {
    expect(segments([0, 100, null, 400], 400, 300, 200)).toEqual([
      [
        { x: 0, y: 200 },
        { x: 100, y: 150 },
      ],
      [{ x: 300, y: 0 }],
    ]);
  });

  it("several nulls in a row are one gap, nulls at the ends are no line", () => {
    expect(segments([null, 50, null, null, 50, null], 100, 500, 100)).toEqual([
      [{ x: 100, y: 50 }],
      [{ x: 400, y: 50 }],
    ]);
  });

  it("max 0: everything on the bottom, no division by zero", () => {
    expect(segments([0, 0], 0, 100, 200)).toEqual([
      [
        { x: 0, y: 200 },
        { x: 100, y: 200 },
      ],
    ]);
  });

  it("a single second sits at the left", () => {
    expect(segments([10], 10, 300, 200)).toEqual([[{ x: 0, y: 0 }]]);
  });

  it("nothing to draw", () => {
    expect(segments([], 0, 300, 200)).toEqual([]);
    expect(segments([null, null], 0, 300, 200)).toEqual([]);
  });
});

function point(second: number, p95: number | null, error_rate = 0): SecondSummary {
  return { second, p50: p95, p95, error_rate: p95 === null ? null : error_rate };
}

function experiment(results: Experiment["results"]): Experiment {
  return {
    id: 1,
    name: "x",
    state: "recover",
    spec: {
      name: "x",
      fault: { kind: "latency", link: "orders-inventory", direction: "both", ms: 200 },
      load: { rate: 10, body: {} },
      phases_s: { baseline: 2, inject: 3, recover: 2 },
      hypothesis: { max_p95_ms: 500, max_error_rate: 0.01 },
    },
    results,
    verdict: null,
    reason: null,
  };
}

const summary = (per_second: SecondSummary[]) => ({
  scheduled: 1,
  outcomes: { ok: 1 },
  latency_ms: { ok: null, all: null },
  per_second,
});

describe("timeline", () => {
  it("puts the phases one after another, by the length in the spec", () => {
    const t = timeline(
      experiment({
        baseline: summary([point(0, 10), point(1, 11)]),
        // the last second of inject had no request, so its series is one point short
        inject: summary([point(0, 210, 0.1), point(1, 220)]),
        recover: summary([point(0, 12), point(1, 13)]),
      }),
    );
    expect(t.p95).toEqual([10, 11, 210, 220, null, 12, 13]);
    expect(t.errorRate).toEqual([0, 0, 0.1, 0, null, 0, 0]);
    expect(t.phaseStarts).toEqual([0, 2, 5]);
  });

  it("a phase not measured yet is empty seconds, so the graph keeps its width", () => {
    const t = timeline(experiment({ baseline: summary([point(0, 10), point(1, 11)]) }));
    expect(t.p95).toEqual([10, 11, null, null, null, null, null]);
  });
});

describe("toPoints", () => {
  it("joins the points the way <polyline> reads them", () => {
    expect(
      toPoints([
        { x: 0, y: 200 },
        { x: 100, y: 150 },
      ]),
    ).toBe("0,200 100,150");
  });

  it("a single point", () => {
    expect(toPoints([{ x: 12.5, y: 0 }])).toBe("12.5,0");
  });
});
