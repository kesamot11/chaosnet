import { useEffect, useState } from "react";
import { END_STATES, type Experiment, fetchExperiment, SPEED, type State } from "./api";

import { remember } from "./progress";

// Sprint 4 decision 3. A demo replay runs SPEED× faster, so it is polled as much more
// often: a new phase is then noticed within 1 s of the recording, as in the real lab (#235).
export const POLL_MS = 1000 / SPEED;
export const RETRY_MS = 30_000; // after no answer; back to POLL_MS once the controller answers

/**
 * The experiment `id`, polled until it reaches an end state (#78).
 *
 * No answer is not an end: after a controller restart, reconcile marks the experiment
 * aborted (#55), and the next answer shows that. Polling stops when the component goes
 * away or `id` changes, and starts again on a new `start`: a demo run replayed again keeps
 * its id (#235).
 */
export function useExperiment(id: number | null, start = 0) {
  const [experiment, setExperiment] = useState<Experiment | null>(null);
  const [unreachable, setUnreachable] = useState(false);

  // biome-ignore lint/correctness/useExhaustiveDependencies: a new `start` polls the same id again
  useEffect(() => {
    setExperiment(null);
    setUnreachable(false);
    if (id === null) return;
    const polling = new AbortController(); // cancels this polling, not the experiment
    let timer: ReturnType<typeof setTimeout> | undefined;
    let previous: State | null = null;

    async function poll(id: number) {
      let wait = POLL_MS;
      try {
        const exp = await fetchExperiment(id, polling.signal);
        if (previous != null && previous !== exp.state) {
          remember(id, exp.state, Date.now());
        }
        previous = exp.state;
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
  }, [id, start]);

  return { experiment, unreachable };
}
