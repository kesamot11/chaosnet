import { END_STATES, type Experiment, JAEGER, type LinkSettings, type Phase } from "./api";
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
          {/* readable at a glance (#209) */}
          <p className={`verdict ${experiment.verdict.passed ? "passed" : "failed"}`}>
            {experiment.verdict.passed ? "passed" : "failed"}
          </p>
          <ul>
            {experiment.verdict.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </div>
      )}
      <h3>Results</h3>
      <table aria-label="results">
        <thead>
          <tr>
            <th>phase</th>
            <th>p50 ms</th>
            <th>p95 ms</th>
            <th>errors %</th>
            <th>degraded %</th>
            <th />
          </tr>
        </thead>
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
                    <td>{s.latency_ms.all?.p50.toFixed(1)}</td>
                    <td>{s.latency_ms.all?.p95.toFixed(1)}</td>
                    <td>{(rate * 100).toFixed(1)}</td>
                    <td>{((degradedRate(s) ?? 0) * 100).toFixed(1)}</td>
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
      <Settings links={experiment.topology?.links ?? null} />
    </section>
  );
}

/** Every link's settings when the experiment ran (#185): the others shape the results too (Tomáš). */
function Settings({ links }: { links: LinkSettings[] | null }) {
  if (links === null) return <p>Settings were not recorded for this experiment.</p>;
  const onOff = (on: boolean) => (on ? "on" : "off");
  return (
    <>
      <h3>Settings when it ran</h3>
      <table aria-label="settings">
        <thead>
          <tr>
            <th>link</th>
            <th>timeout s</th>
            <th>retries</th>
            <th>backoff s</th>
            <th>breaker</th>
            <th>budget</th>
            <th>fallback</th>
          </tr>
        </thead>
        <tbody>
          {links.map((l) => (
            <tr key={`${l.from}-${l.to}`}>
              <th scope="row">
                {l.from} → {l.to}
              </th>
              <td>{l.timeout_s}</td>
              <td>{l.max_retries}</td>
              <td>{l.backoff_s}</td>
              <td>{onOff(l.breaker)}</td>
              <td>{l.retry_budget ?? "off"}</td>
              <td>{onOff(l.fallback)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
