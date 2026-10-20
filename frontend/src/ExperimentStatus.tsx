import { END_STATES, type Experiment, type Phase } from "./api";

import { errorRate } from "./results";

type Props = {
  experiment: Experiment; // the latest answer of the poll
  unreachable: boolean; // the last poll got no answer; `experiment` is the last known state
  onAbort: () => void;
};

const PHASES: Phase[] = ["baseline", "inject", "recover"];

/** State, per-phase results and verdict of one experiment (#78); contract in the tests. */
export function ExperimentStatus({ experiment, unreachable, onAbort }: Props) {
  const n = PHASES.indexOf(experiment.state as Phase) + 1;
  return (
    <section>
      <h2>
        {experiment.name}: {experiment.state} {n > 0 && `(${n}/3)`}
      </h2>
      {!END_STATES.has(experiment.state) && (
        <button type="button" onClick={onAbort}>
          Abort
        </button>
      )}
      {unreachable && <p>Controller not reachable, retrying…</p>}
      {experiment.reason !== null && <p>{experiment.reason}</p>}
      {experiment.verdict !== null && (
        <div>
          <p>{experiment.verdict.passed ? "passed" : "failed"}</p>
          <ul>
            {experiment.verdict.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </div>
      )}
      <table>
        <tbody>
          {PHASES.map((p) => {
            const s = experiment.results[p];
            const rate = s === undefined ? null : errorRate(s);
            return (
              <tr key={p}>
                <th>{p}</th>
                {s === undefined && (
                  <>
                    <td>-</td>
                    <td>-</td>
                    <td>-</td>
                  </>
                )}
                {s !== undefined && rate === null && <td>no requests</td>}
                {s !== undefined && rate !== null && (
                  <>
                    <td>{s.latency_ms.all?.p50.toFixed(1)} ms</td>
                    <td>{s.latency_ms.all?.p95.toFixed(1)} ms</td>
                    <td>{(rate * 100).toFixed(1)} %</td>
                  </>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}
