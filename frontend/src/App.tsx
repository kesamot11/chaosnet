import { useEffect, useState } from "react";
import { abortExperiment, fetchTopology, type Topology } from "./api";
import { ExperimentForm } from "./ExperimentForm";
import { ExperimentStatus } from "./ExperimentStatus";
import { LatencyChart } from "./LatencyChart";
import { TopologyView } from "./TopologyView";
import { useExperiment } from "./useExperiment";

export function App() {
  const [topology, setTopology] = useState<Topology | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  // The experiment started last; it outlives the form, which follows the selected link.
  const [experimentId, setExperimentId] = useState<number | null>(null);
  const { experiment, unreachable } = useExperiment(experimentId);

  useEffect(() => {
    const controller = new AbortController();
    fetchTopology(controller.signal)
      .then(setTopology)
      .catch((e: unknown) => {
        if (!controller.signal.aborted) setError(e instanceof Error ? e.message : String(e));
      });
    return () => controller.abort(); // the component went away: stop the request
  }, []);

  return (
    <main>
      <h1>ChaosNet</h1>
      {error !== null && <p>Controller not reachable: {error}</p>}
      {error === null && topology === null && <p>Loading the lab…</p>}
      {topology !== null && (
        <>
          <TopologyView topology={topology} selected={selected} onSelect={setSelected} />
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
