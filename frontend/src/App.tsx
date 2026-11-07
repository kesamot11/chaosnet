import { useEffect, useState } from "react";
import {
  abortExperiment,
  fetchExperiments,
  fetchTopology,
  type LabStatus,
  saveTopology,
  type Topology,
} from "./api";
import { Drawer, type Side } from "./Drawer";
import { Editor } from "./Editor";
import { ExperimentForm } from "./ExperimentForm";
import { ExperimentStatus } from "./ExperimentStatus";
import { addLink, addService, removeLink, removeService, withPosition, withSettings } from "./edit";
import { LatencyChart } from "./LatencyChart";
import { LinkPanel } from "./LinkPanel";
import { TopologyView } from "./TopologyView";
import { useExperiment } from "./useExperiment";
import { useLab } from "./useLab";
import { useMove } from "./useMove";

export function App() {
  const [topology, setTopology] = useState<Topology | null>(null);
  const [error, setError] = useState<string | null>(null);
  // One selected thing at a time, a link (the fault form, Remove) or a service (Remove) (Tomáš).
  const [selection, setSelection] = useState<Selection | null>(null);
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

  // Changes of the lab wait in a draft until Save (#193); while there is one, a move is part
  // of it too, or saving the move would apply the draft (Tomáš).
  const [draft, setDraft] = useState<Topology | null>(null);
  const [saving, setSaving] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const [notAdded, setNotAdded] = useState<string | null>(null); // why a drawn link was not
  // All closed at start: the lab gets the whole screen (Tomáš, #207).
  const [open, setOpen] = useState<Record<Side, boolean>>({
    left: false,
    right: false,
    bottom: false,
  });
  const toggle = (side: Side) => setOpen((o) => ({ ...o, [side]: !o[side] }));
  const shown = draft ?? topology;
  // A selection counts only while its link or service is shown: a rollback or a removal may
  // take it away, and nothing should point at what is gone.
  const shownSelection = selection !== null && shows(shown, selection) ? selection : null;
  const selected = shownSelection?.kind === "link" ? shownSelection.name : null;
  const service = shownSelection?.kind === "service" ? shownSelection.name : null;
  const link = shown?.links.find((l) => l.name === selected);

  function edit(change: (t: Topology) => Topology) {
    if (shown !== null) setDraft(change(shown));
    setNotAdded(null); // an old "not added" would read as about this change
  }

  function connect(from: string, to: string) {
    if (shown === null) return;
    const result = addLink(shown, from, to);
    if (typeof result === "string") setNotAdded(result);
    else edit(() => result);
  }

  function remove() {
    if (shownSelection === null) return;
    const { kind, name } = shownSelection;
    edit((t) => (kind === "link" ? removeLink(t, name) : removeService(t, name)));
    setSelection(null);
  }

  async function save() {
    if (draft === null) return;
    setSaving(true);
    const saved = await saveTopology(draft);
    setSaving(false);
    setRefused(saved.ok ? null : saved.reason);
    if (!saved.ok) setOpen((o) => ({ ...o, left: true })); // why, next to what to fix (Tomáš, #208)
    if (saved.ok) {
      setTopology(saved.topology);
      setDraft(null); // the lab now restarts: LabLine shows it
    }
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
    <main className="app">
      <header className="topbar">
        <h1>ChaosNet</h1>
        {error !== null && <p role="alert">Controller not reachable: {error}</p>}
        {error === null && topology === null && <p>Loading the lab…</p>}
        {lab !== null && <LabLine lab={lab} />}
        {draft !== null && (
          // seen and saved with the editor closed too (Tomáš, #208); the same save as the editor's
          <div className="unsaved">
            <p>Unsaved changes</p>
            <button type="button" className="primary" disabled={saving} onClick={save}>
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        )}
        {notAdded !== null && <p role="alert">{notAdded}</p>}
        {notSaved !== null && <p role="alert">Not saved: {notSaved}</p>}
      </header>
      {shown !== null && (
        <div className="stage">
          <TopologyView
            topology={shown}
            selected={selected}
            onSelect={(name) => {
              setSelection({ kind: "link", name });
              setOpen((o) => ({ ...o, left: true, right: true })); // settings and the form (Tomáš)
            }}
            onMove={draft === null ? move : (s, p) => edit((t) => withPosition(t, s, p))}
            service={service}
            onSelectService={(name) => {
              setSelection({ kind: "service", name });
              setOpen((o) => ({ ...o, left: true })); // Remove is there (Tomáš)
            }}
            onConnect={connect}
            // a fault is in the lab only during inject (Tomáš)
            faulted={experiment?.state === "inject" ? experiment.spec.fault.link : null}
          />
          <Drawer side="left" label="Editor" open={open.left} onToggle={() => toggle("left")}>
            <Editor
              changed={draft !== null}
              removable={selected !== null ? `link ${selected}` : service}
              saving={saving}
              refused={refused}
              onAdd={(name) => edit((t) => addService(t, name))}
              onRemove={remove}
              onSave={save}
            >
              {link !== undefined && (
                <LinkPanel
                  link={link}
                  onChange={(c) => edit((t) => withSettings(t, link.name, c))}
                />
              )}
            </Editor>
          </Drawer>
          <Drawer
            side="right"
            label="Experiment"
            open={open.right}
            onToggle={() => toggle("right")}
          >
            <p>
              {selected === null
                ? "Click a link to choose where the fault goes."
                : `Selected link: ${selected}`}
            </p>
            {link?.available && draft !== null && (
              // Start stays allowed (Tomáš), but the lab changes only on Save
              <p role="note">
                Unsaved changes: an experiment started now runs with the saved settings.
              </p>
            )}
            {link?.available && (
              <ExperimentForm
                link={link.name}
                onStarted={(id) => {
                  setExperimentId(id);
                  setOpen((o) => ({ ...o, bottom: true })); // the chart starts to fill (Tomáš)
                }}
              />
            )}
            {link !== undefined && !link.available && (
              // a drawn link gets its proxy on Save; a saved one has lost it (Tomáš's review)
              <p>
                {topology?.links.some((l) => l.name === link.name)
                  ? "This link has no proxy, so no fault can be added."
                  : "Save the lab, then you can add a fault here."}
              </p>
            )}
            {experiment !== null && (
              <ExperimentStatus
                experiment={experiment}
                unreachable={unreachable}
                // A refused abort shows up in the next poll: the experiment is no longer running.
                onAbort={() => abortExperiment(experiment.id)}
              />
            )}
          </Drawer>
          <Drawer
            side="bottom"
            label="Latency"
            open={open.bottom}
            onToggle={() => toggle("bottom")}
          >
            {experiment !== null ? (
              <LatencyChart experiment={experiment} />
            ) : (
              <p>Start an experiment to see its latency here.</p>
            )}
          </Drawer>
        </div>
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

type Selection = { kind: "link" | "service"; name: string };

function shows(topology: Topology | null, selection: Selection): boolean {
  const names =
    selection.kind === "link"
      ? (topology?.links ?? []).map((l) => `${l.from}-${l.to}`)
      : (topology?.services ?? []).map((s) => s.name);
  return names.includes(selection.name);
}
