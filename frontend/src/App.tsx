import { useEffect, useState } from "react";
import {
  abortExperiment,
  fetchExperiments,
  fetchTopology,
  type LabStatus,
  type Topology,
} from "./api";
import { ExperimentForm } from "./ExperimentForm";
import { ExperimentStatus } from "./ExperimentStatus";
import { LatencyChart } from "./LatencyChart";
import { TopologyView } from "./TopologyView";
import { useExperiment } from "./useExperiment";
import { useLab } from "./useLab";
import { useMove } from "./useMove";

export function App() {
  const [topology, setTopology] = useState<Topology | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  // The experiment started last; it outlives the form, which follows the selected link.
  const [experimentId, setExperimentId] = useState<number | null>(null);
  const { experiment, unreachable } = useExperiment(experimentId);
  // When a restart ends, the topology may be the previous one again (a rollback, #191).
  const lab = useLab(() => {
    fetchTopology()
      .then(setTopology)
      .catch(() => {}); // no answer: the next restart or a reload shows it
  });

  const { move, notSaved } = useMove(topology, setTopology); // a dropped service (#192)

  useEffect(() => {
    const request = new AbortController();
    fetchTopology(request.signal)
      .then(setTopology)
      .catch((e: unknown) => {
        if (!request.signal.aborted) setError(e instanceof Error ? e.message : String(e));
      });
    return () => request.abort(); // the component went away: stop the request
  }, []);

  // After a refresh: follow the newest experiment, running or the last one (#172).
  useEffect(() => {
    const request = new AbortController();
    fetchExperiments(request.signal)
      .then((list) => {
        const newest = list[0]; // undefined when there are no experiments yet
        if (newest === undefined) return;
        setExperimentId((current) => current ?? newest.id);
      })
      .catch(() => {}); // no list: just the form; the topology request already reports a lost controller
    return () => request.abort();
  }, []);

  return (
    <main>
      <h1>ChaosNet</h1>
      {error !== null && <p>Controller not reachable: {error}</p>}
      {error === null && topology === null && <p>Loading the lab…</p>}
      {topology !== null && (
        <>
          {lab !== null && <LabLine lab={lab} />}
          <TopologyView
            topology={topology}
            selected={selected}
            onSelect={setSelected}
            onMove={move}
          />
          {notSaved !== null && <p role="alert">Not saved: {notSaved}</p>}
          <p>
            {selected === null
              ? "Click a link to choose where the fault goes."
              : `Selected link: ${selected}`}
          </p>
          {selected !== null && <ExperimentForm link={selected} onStarted={setExperimentId} />}
          {experiment !== null && (
            <ExperimentStatus
              experiment={experiment}
              unreachable={unreachable}
              // A refused abort shows up in the next poll: the experiment is no longer running.
              onAbort={() => abortExperiment(experiment.id)}
            />
          )}
          {experiment !== null && <LatencyChart experiment={experiment} />}
        </>
      )}
    </main>
  );
}

/** What the lab is doing, for the user (#191, #192; the words are Tomáš's). */
export function LabLine({ lab }: { lab: LabStatus }) {
  if (lab.state === "restarting") return <p>The lab is restarting, hold on a moment…</p>;
  if (lab.state === "failed") return <p role="alert">The lab failed: {lab.error}</p>;
  if (lab.error !== null) {
    return <p role="alert">The last change failed, so the previous lab is back: {lab.error}</p>;
  }
  return <p>The lab is running.</p>;
}
