import { useState } from "react";

type Props = {
  changed: boolean; // the draft differs from the saved topology
  removable: string | null; // what Remove removes: the selected service or link
  saving: boolean;
  refused: string | null; // why the last save was refused
  onAdd: (name: string) => void;
  onRemove: () => void;
  onSave: () => void;
};

/**
 * Change the lab (#193, #194): add and remove services and links; Save applies the draft (ADR-011). A name is
 * checked by the controller on Save, not here: one copy of the rule (Tomáš).
 */
export function Editor({ changed, removable, saving, refused, onAdd, onRemove, onSave }: Props) {
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
      {removable !== null && (
        <button type="button" onClick={onRemove}>
          Remove {removable}
        </button>
      )}
      <button type="button" className="primary" disabled={!changed || saving} onClick={onSave}>
        {saving ? "Saving…" : "Save"}
      </button>
      {changed && <span> Unsaved changes</span>}
      {refused !== null && <p role="alert">Not saved: {refused}</p>}
    </section>
  );
}
