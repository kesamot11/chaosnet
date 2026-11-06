import { useState } from "react";

type Props = {
  changed: boolean; // the draft differs from the saved topology
  service: string | null; // the selected service
  saving: boolean;
  refused: string | null; // why the last save was refused
  onAdd: (name: string) => void;
  onRemove: (name: string) => void;
  onSave: () => void;
};

/**
 * Change the lab (#193): add and remove services; Save applies the draft (ADR-011). A name is
 * checked by the controller on Save, not here: one copy of the rule (Tomáš).
 */
export function Editor({ changed, service, saving, refused, onAdd, onRemove, onSave }: Props) {
  const [name, setName] = useState("");
  return (
    <section aria-label="editor">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (name === "") return;
          onAdd(name);
          setName("");
        }}
      >
        <label>
          New service <input value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <button type="submit">Add</button>
      </form>
      {service !== null && (
        <button type="button" onClick={() => onRemove(service)}>
          Remove {service}
        </button>
      )}
      <button type="button" disabled={!changed || saving} onClick={onSave}>
        {saving ? "Saving…" : "Save"}
      </button>
      {changed && <span> Unsaved changes</span>}
      {refused !== null && <p role="alert">Not saved: {refused}</p>}
    </section>
  );
}
