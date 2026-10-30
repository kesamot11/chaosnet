import { useEffect, useState } from "react";
import { END_STATES, type Experiment, fetchExperiment } from "./api";

export const POLL_MS = 1000; // Sprint 4 decision 3
export const RETRY_MS = 30_000; // after no answer; back to POLL_MS once the controller answers

/**
 * The experiment `id`, polled until it reaches an end state (#78).
 *
 * No answer is not an end: after a controller restart, reconcile marks the experiment
 * aborted (#55), and the next answer shows that. Polling stops when the component goes
 * away or `id` changes.
 */
export function useExperiment(id: number | null) {
  const [experiment, setExperiment] = useState<Experiment | null>(null);
  const [unreachable, setUnreachable] = useState(false);

  useEffect(() => {
    setExperiment(null);
    setUnreachable(false);
    if (id === null) return;
    const polling = new AbortController(); // cancels this polling, not the experiment
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll(id: number) {
      let wait = POLL_MS;
      try {
        const exp = await fetchExperiment(id, polling.signal);
        setExperiment(exp);
        setUnreachable(false);
        if (END_STATES.has(exp.state)) return;
      } catch {
        if (polling.signal.aborted) return; // stopped on purpose, not a lost controller
        setUnreachable(true);
        wait = RETRY_MS;
      }
      timer = setTimeout(() => poll(id), wait);
    }

    poll(id);
    return () => {
      polling.abort(); // also cancels a request still on its way
      clearTimeout(timer);
    };
  }, [id]);

  return { experiment, unreachable };
}
