import { useEffect, useState } from "react";
import {
  abortExperiment,
  fetchExperiments,
  fetchTopology,
  saveTopology,
  type Topology,
} from "./api";
import { ExperimentForm } from "./ExperimentForm";
import { ExperimentStatus } from "./ExperimentStatus";
import { LatencyChart } from "./LatencyChart";
import type { Position } from "./layout";
import { TopologyView } from "./TopologyView";
import { useExperiment } from "./useExperiment";

export function App() {
  const [topology, setTopology] = useState<Topology | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  // The experiment started last; it outlives the form, which follows the selected link.
  const [experimentId, setExperimentId] = useState<number | null>(null);
  const { experiment, unreachable } = useExperiment(experimentId);
  const [notSaved, setNotSaved] = useState<string | null>(null);

  // A dropped service is saved at once (#192, Tomáš): only its position changed, so the
  // controller saves it without touching the lab. Refused: it goes back where it was.
  async function move(service: string, position: Position) {
    if (topology === null) return;
    const moved: Topology = {
      ...topology,
      services: topology.services.map((s) => (s.name === service ? { ...s, ...position } : s)),
    };
    setTopology(moved);
    const saved = await saveTopology(moved);
    setTopology(saved.ok ? saved.topology : topology);
    setNotSaved(saved.ok ? null : saved.reason);
  }

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
