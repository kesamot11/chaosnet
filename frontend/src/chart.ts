/** From an experiment to lines in pixels, for the latency graph (#79). */

import type { Experiment, Phase } from "./api";

const PHASES: Phase[] = ["baseline", "inject", "recover"];

export type Timeline = {
  p95: (number | null)[]; // one value per second of the whole experiment
  errorRate: (number | null)[];
  phaseStarts: number[]; // the second where each phase starts: [0, baseline, baseline + inject]
};

/**
 * The three phases on one time axis. Each phase takes as many seconds as its spec says,
 * not as many as it has points: a last second without requests would otherwise shift
 * every later phase to the left. A second without data, or a phase not measured yet,
 * is null.
 */
export function timeline(experiment: Experiment): Timeline {
  const result: Timeline = { p95: [], errorRate: [], phaseStarts: [] };
  for (const phase of PHASES) {
    result.phaseStarts.push(result.p95.length);
    const seconds = Math.ceil(experiment.spec.phases_s[phase]);
    const series = experiment.results[phase]?.per_second ?? [];
    for (let s = 0; s < seconds; s++) {
      const point = series[s];
      result.p95.push(point?.p95 ?? null);
      result.errorRate.push(point?.error_rate ?? null);
    }
  }
  return result;
}

export type Point = { x: number; y: number };

/**
 * Values (one per second) as lines in a `width` x `height` box: second 0 at the left,
 * the last second at the right, 0 at the bottom, `max` at the top. A null breaks the
 * line, so a second without data is a gap and not a value nobody measured.
 */
export function segments(
  values: (number | null)[],
  max: number,
  width: number,
  height: number,
): Point[][] {
  const res = [];
  for (let i = 0; i < values.length; i++) {
    if (values[i] == null) {
      continue;
    }
    const segment: Point[] = [];
    while (values[i] != null && i < values.length) {
      const value = values[i] ?? 0;
      const step = values.length > 1 ? width / (values.length - 1) : 0;
      segment.push({ x: i * step, y: max === 0 ? height : height - (value / max) * height });
      i++;
    }
    res.push(segment);
  }
  return res;
}

/** A line for SVG's <polyline points="...">: "x,y x,y ...", e.g. "0,200 100,150". */
export function toPoints(segment: Point[]): string {
  return segment.map((p) => `${p.x},${p.y}`).join(" ");
}
