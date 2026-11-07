import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { Drawer } from "./Drawer";

test("a closed drawer can't be reached by the keyboard; its handle toggles it", () => {
  const onToggle = vi.fn();
  const { rerender } = render(
    <Drawer side="left" label="Editor" open={false} onToggle={onToggle}>
      <button type="button">Save</button>
    </Drawer>,
  );
  const body = screen.getByRole("button", { name: "Save", hidden: true }).parentElement;
  expect(body).toHaveAttribute("inert");
  fireEvent.click(screen.getByRole("button", { name: "Editor" }));
  expect(onToggle).toHaveBeenCalledOnce();

  rerender(
    <Drawer side="left" label="Editor" open onToggle={onToggle}>
      <button type="button">Save</button>
    </Drawer>,
  );
  expect(body).not.toHaveAttribute("inert");
  expect(screen.getByRole("button", { name: "Editor" })).toHaveAttribute("aria-expanded", "true");
});
