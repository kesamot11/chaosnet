import { type Dispatch, type SetStateAction, useRef, useState } from "react";
import { saveTopology, type Topology } from "./api";
import { withPosition } from "./edit";
import type { Position } from "./layout";

/**
 * Save where a service was dropped, at once (#192, Tomáš): only a position changed, so the
 * controller saves it without touching the lab.
 *
 * Quick drops one after another (Tomáš's review): one save at a time, in the order of the
 * drops, so the controller ends with the last; only the last drop's answer is shown, so a
 * service never jumps back. A refused save puts the services where they were before it.
 */
export function useMove(
  topology: Topology | null,
  setTopology: Dispatch<SetStateAction<Topology | null>>,
) {
  const [notSaved, setNotSaved] = useState<string | null>(null);
  const saves = useRef<Promise<void>>(Promise.resolve()); // the saves so far, one after another
  const drops = useRef(0);

  function move(service: string, position: Position) {
    if (topology === null) return;
    const before = topology;
    const moved = withPosition(topology, service, position);
    setTopology(moved);
    drops.current += 1;
    const drop = drops.current;
    saves.current = saves.current.then(async () => {
      const saved = await saveTopology(moved);
      if (drop !== drops.current) return; // a later drop's save follows; its answer is shown
      setTopology(saved.ok ? saved.topology : before);
      setNotSaved(saved.ok ? null : saved.reason);
    });
  }

  return { move, notSaved };
}
