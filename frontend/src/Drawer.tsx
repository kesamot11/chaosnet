import type { ReactNode } from "react";

export type Side = "left" | "right" | "bottom";

type Props = {
  side: Side;
  label: string; // names the drawer and its handle, e.g. "Editor"
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
};

/**
 * A panel over the lab that slides in and out on a click of its handle (#207, Tomáš): it
 * covers the lab instead of narrowing it. While closed it stays in the page, but `inert`,
 * so the keyboard can't reach what can't be seen.
 */
export function Drawer({ side, label, open, onToggle, children }: Props) {
  const id = `drawer-${side}`;
  return (
    <aside className={`drawer drawer-${side}${open ? " open" : ""}`} aria-label={label}>
      <button
        type="button"
        className="drawer-handle"
        aria-expanded={open}
        aria-controls={id}
        onClick={onToggle}
      >
        {label}
      </button>
      <div id={id} className="drawer-body" inert={!open}>
        {children}
      </div>
    </aside>
  );
}
