import { useEffect, useRef, useState } from "react";
import { fetchLab, type LabState, type LabStatus } from "./api";
import { POLL_MS } from "./useExperiment";

/**
 * The lab's state from GET /lab (#191), polled every second. `onSettled` runs when a restart
 * has ended, so the page loads the topology again: after a rollback it is the previous one.
 */
export function useLab(onSettled: () => void): LabStatus | null {
  const [lab, setLab] = useState<LabStatus | null>(null);
  const settled = useRef(onSettled); // the latest callback, without restarting the polling
  settled.current = onSettled;

  useEffect(() => {
    const polling = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let previous: LabState | null = null;

    async function poll() {
      try {
        const status = await fetchLab(polling.signal);
        if (previous === "restarting" && status.state !== "restarting") settled.current();
        previous = status.state;
        setLab(status);
      } catch {
        if (polling.signal.aborted) return; // stopped on purpose
      }
      timer = setTimeout(poll, POLL_MS);
    }

    poll();
    return () => {
      polling.abort();
      clearTimeout(timer);
    };
  }, []);

  return lab;
}
