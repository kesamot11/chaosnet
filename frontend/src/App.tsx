import { useEffect, useState } from "react";

type Status = "checking" | "up" | "down";

/** The first screen: says whether the controller answers. The topology view comes in #76. */
export function App() {
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/experiments", { signal: controller.signal })
      .then((res) => setStatus(res.ok ? "up" : "down"))
      .catch(() => {
        if (!controller.signal.aborted) setStatus("down");
      });
    return () => controller.abort();
  }, []);

  return (
    <main>
      <h1>ChaosNet</h1>
      <p>
        Controller:{" "}
        {status === "checking" ? "checking…" : status === "up" ? "running" : "not reachable"}
      </p>
    </main>
  );
}
