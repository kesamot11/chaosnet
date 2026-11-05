import { END_STATES, type Experiment, JAEGER, type Phase } from "./api";
import { phaseProgress, recall } from "./progress";
import { degradedRate, errorRate } from "./results";

type Props = {
  experiment: Experiment; // the latest answer of the poll
  unreachable: boolean; // the last poll got no answer; `experiment` is the last known state
  onAbort: () => void;
};

const PHASES: Phase[] = ["baseline", "inject", "recover"];

function PhaseBar({ experiment }: { experiment: Experiment }) {
  const phase = experiment.state as Phase;
  const total_s = experiment.spec.phases_s[phase];
  const p = phaseProgress(recall(experiment.id, phase), total_s, Date.now());
  if (p.kind === "unknown") {
    return (
      <p>
        This page wasn't open when the phase started, so there is no progress bar. The phase lasts{" "}
        {p.total_s} s.
      </p>
    );
  }
  if (p.kind === "waiting") {
    return (
      <p>
        <progress value={1} max={1} /> waiting for requests in flight
      </p>
    );
  }
  return (
    <p>
      <progress value={p.elapsed_s} max={p.total_s} /> {Math.round(p.elapsed_s)} s of {p.total_s} s
    </p>
  );
}

/** State, per-phase results and verdict of one experiment (#78); contract in the tests. */
export function ExperimentStatus({ experiment, unreachable, onAbort }: Props) {
  const n = PHASES.indexOf(experiment.state as Phase) + 1;
  return (
    <section>
      <h2>
        {experiment.name}: {experiment.state} {n > 0 && `(${n}/3)`}
      </h2>
      {n > 0 && <PhaseBar experiment={experiment} />}
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
                    <td>-</td>
                  </>
                )}
                {s !== undefined && rate === null && <td>no requests</td>}
                {s !== undefined && rate !== null && (
                  <>
                    <td>{s.latency_ms.all?.p50.toFixed(1)} ms</td>
                    <td>{s.latency_ms.all?.p95.toFixed(1)} ms</td>
                    <td>{(rate * 100).toFixed(1)} %</td>
                    <td>{((degradedRate(s) ?? 0) * 100).toFixed(1)} % degraded</td>
                    <td>
                      {s.example_trace && <a href={`${JAEGER}/trace/${s.example_trace}`}>trace</a>}
                    </td>
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
