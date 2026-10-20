import type { Experiment } from "./api";

type Props = {
  experiment: Experiment; // the latest answer of the poll
  unreachable: boolean; // the last poll got no answer; `experiment` is the last known state
  onAbort: () => void;
};

/** State, per-phase results and verdict of one experiment (#78); contract in the tests. */
export function ExperimentStatus({ experiment, unreachable, onAbort }: Props) {
  // Tomáš (#78)
  return null;
}
