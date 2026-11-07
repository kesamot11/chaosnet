import { type ReactNode, useRef, useState } from "react";

export type Side = "left" | "right" | "bottom";

type Props = {
  side: Side;
  label: string; // names the drawer and its handle, e.g. "Editor"
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
};

const MIN_HEIGHT = 120; // px; the bottom panel never shrinks below its chart's caption
const STEP = 40; // px per arrow key

/**
 * A panel over the lab that slides in and out on a click of its handle (#207, Tomáš): it
 * covers the lab instead of narrowing it. While closed it stays in the page, but `inert`,
 * so the keyboard can't reach what can't be seen. The bottom one can be made taller or
 * shorter by dragging its top edge (Tomáš).
 */
export function Drawer({ side, label, open, onToggle, children }: Props) {
  const id = `drawer-${side}`;
  const [height, setHeight] = useState<number | null>(null); // null: the CSS default
  const drag = useRef<number | null>(null); // the panel's bottom edge while dragging

  function resize(to: number, aside: HTMLElement) {
    const stage = aside.parentElement?.clientHeight ?? Number.POSITIVE_INFINITY;
    // keep a strip of the lab above it, and never less than MIN_HEIGHT
    setHeight(Math.round(Math.max(Math.min(to, stage - 40), MIN_HEIGHT)));
  }

  return (
    <aside
      className={`drawer drawer-${side}${open ? " open" : ""}`}
      aria-label={label}
      style={height !== null ? { height } : undefined}
    >
      <button
        type="button"
        className="drawer-handle"
        aria-expanded={open}
        aria-controls={id}
        onClick={onToggle}
      >
        {label}
      </button>
      {side === "bottom" && open && (
        // biome-ignore lint/a11y/useSemanticElements: an <hr> can't be dragged or focused
        <div
          className="drawer-resize"
          role="separator"
          aria-orientation="horizontal"
          aria-label={`Resize ${label}`}
          aria-valuenow={height ?? undefined}
          tabIndex={0}
          onPointerDown={(e) => {
            e.currentTarget.setPointerCapture(e.pointerId);
            drag.current = e.currentTarget.parentElement?.getBoundingClientRect().bottom ?? null;
          }}
          onPointerMove={(e) => {
            const aside = e.currentTarget.parentElement;
            if (drag.current !== null && aside) resize(drag.current - e.clientY, aside);
          }}
          onPointerUp={() => {
            drag.current = null;
          }}
          onKeyDown={(e) => {
            const aside = e.currentTarget.parentElement;
            if (!aside || (e.key !== "ArrowUp" && e.key !== "ArrowDown")) return;
            e.preventDefault();
            resize(aside.clientHeight + (e.key === "ArrowUp" ? STEP : -STEP), aside);
          }}
        />
      )}
      <div id={id} className="drawer-body" inert={!open}>
        {children}
      </div>
    </aside>
  );
}
