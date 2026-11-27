import type { Experiment, Phase, Topology } from "./api";

const PHASES: Phase[] = ["baseline", "inject", "recover"];

/**
 * A recorded run as the controller showed it `elapsed_s` seconds after its start (#234,
 * ADR-012): as in a real run, a phase's results appear when the phase ends, and the
 * verdict at the end. Nothing is changed, only shown later.
 */
export function replayed(run: Experiment, elapsed_s: number): Experiment {
  let end = 0;
  const results: Experiment["results"] = {};
  for (const phase of PHASES) {
    end += run.spec.phases_s[phase];
    if (elapsed_s < end) {
      const alarms = run.alarms?.filter((a) => a.at_s <= elapsed_s); // only the ones so far
      return { ...run, state: phase, results, verdict: null, reason: null, alarms };
    }
    const measured = run.results[phase];
    if (measured) results[phase] = measured;
  }
  return run; // the end: completed (or how it really ended), with its verdict
}

/** The lab a run was recorded on, from the links it recorded (#185); placed by layout.ts. */
export function topologyOf(run: Experiment): Topology {
  const links = run.topology?.links ?? [];
  const names = [...new Set(links.flatMap((l) => [l.from, l.to]))];
  return {
    version: 1,
    services: names.map((name) => ({ name, port: null })),
    links: links.map((l) => ({ ...l, name: `${l.from}-${l.to}`, available: true })),
  };
}
