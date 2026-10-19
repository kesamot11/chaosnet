import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { App } from "./App";
import type { Topology } from "./api";

const LAB: Topology = {
  version: 1,
  services: [
    { name: "gateway", port: 8080 },
    { name: "orders", port: null },
  ],
  links: [
    {
      from: "gateway",
      to: "orders",
      timeout_s: 2,
      max_retries: 1,
      name: "gateway-orders",
      available: true,
    },
  ],
};

afterEach(() => {
  vi.unstubAllGlobals();
});

test("shows the lab from the controller", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(LAB))));
  render(<App />);
  expect(await screen.findByText("gateway :8080")).toBeInTheDocument();
  expect(screen.getByText(/Click a link/)).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledWith("/api/topology", expect.anything());
});

test("says when the controller is not reachable", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
  render(<App />);
  expect(await screen.findByText(/not reachable: Failed to fetch/)).toBeInTheDocument();
});
