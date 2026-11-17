import { type FormEvent, useState } from "react";
import { type Run, replay } from "./api";
import { remember } from "./progress";

type Props = {
  link: string;
  runs: Run[]; // the runs recorded on this link (demo/runs.json)
  onStarted: (id: number) => void;
  running: boolean; // one replay at a time: Start waits, and says why (Tomáš, #235)
};

/** The demo's small experiment form (#235): pick a recorded run on the link, then Start. */
export function ReplayForm({ link, runs, onStarted, running }: Props) {
  const [chosen, setChosen] = useState(runs[0]?.id);

  function submit(e: FormEvent) {
    e.preventDefault(); // a plain HTML form would reload the page
    if (chosen === undefined) return;
    replay(chosen);
    remember(chosen, "baseline", Date.now());
    onStarted(chosen);
  }

  if (runs.length === 0) return <p>No run was recorded on {link}.</p>;
  return (
    <form onSubmit={submit} aria-label="replay">
      <h2>Experiment on {link}</h2>
      <fieldset>
        <legend>Recorded runs</legend>
        {runs.map((run) => (
          <label key={run.id}>
            <input
              type="radio"
              name="run"
              checked={chosen === run.id}
              onChange={() => setChosen(run.id)}
            />
            <span>
              <strong>{run.name}</strong> {run.about}
            </span>
          </label>
        ))}
      </fieldset>
      <div className="start">
        <button type="submit" className="primary" disabled={running}>
          Start
        </button>
        {running && <p>A replay is running.</p>}
      </div>
    </form>
  );
}
