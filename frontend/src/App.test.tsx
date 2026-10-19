import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { App } from "./App";

afterEach(() => {
  vi.unstubAllGlobals();
});

test("shows that the controller is running", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("[]")));
  render(<App />);
  expect(await screen.findByText(/running/)).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledWith("/api/experiments", expect.anything());
});

test("shows that the controller is not reachable", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
  render(<App />);
  expect(await screen.findByText(/not reachable/)).toBeInTheDocument();
});
