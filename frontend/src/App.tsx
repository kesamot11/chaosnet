import { useEffect, useState } from "react";
import { fetchTopology, type Topology } from "./api";
import { TopologyView } from "./TopologyView";

export function App() {
  const [topology, setTopology] = useState<Topology | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

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
        </>
      )}
    </main>
  );
}
