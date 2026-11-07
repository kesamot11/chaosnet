import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import type { Topology } from "./api";
import { TopologyView, toNodes } from "./TopologyView";

const LAB: Topology = {
  version: 1,
  services: [
    { name: "gateway", port: 8080 },
    { name: "orders", port: null },
    { name: "inventory", port: null },
  ],
  links: [
    {
      from: "gateway",
      to: "orders",
      timeout_s: 2,
      max_retries: 1,
      backoff_s: 0,
      breaker: false,
      retry_budget: null,
      fallback: false,
      name: "gateway-orders",
      available: false,
    },
    {
      from: "orders",
      to: "inventory",
      timeout_s: 0.5,
      max_retries: 2,
      backoff_s: 0,
      breaker: false,
      retry_budget: null,
      fallback: false,
      name: "orders-inventory",
      available: true,
    },
  ],
};

function clickLink(name: string) {
  const edge = document.querySelector(`[data-id="${name}"]`);
  if (!edge) throw new Error(`edge ${name} was not drawn`);
  fireEvent.click(edge);
}

test("draws every service and link", async () => {
  render(<TopologyView topology={LAB} selected={null} onSelect={() => {}} onMove={() => {}} />);
  expect(await screen.findByText("gateway :8080")).toBeInTheDocument();
  expect(screen.getByText("orders")).toBeInTheDocument();
  expect(screen.getByText("inventory")).toBeInTheDocument();
  expect(await screen.findByText("0.5 s, 2 retries")).toBeInTheDocument();
  expect(screen.getByText("no proxy")).toBeInTheDocument();
});

test("clicking an available link selects it", async () => {
  const onSelect = vi.fn();
  render(<TopologyView topology={LAB} selected={null} onSelect={onSelect} onMove={() => {}} />);
  await screen.findByText("0.5 s, 2 retries");
  clickLink("orders-inventory");
  expect(onSelect).toHaveBeenCalledWith("orders-inventory");
});

test("a link without a proxy can be selected too, to remove it (Tomáš, #194)", async () => {
  const onSelect = vi.fn();
  render(<TopologyView topology={LAB} selected={null} onSelect={onSelect} onMove={() => {}} />);
  await screen.findByText("no proxy");
  clickLink("gateway-orders");
  expect(onSelect).toHaveBeenCalledWith("gateway-orders");
});

test("a service drawn where it was dropped, the others where layout.ts puts them (#192)", () => {
  const moved: Topology = {
    ...LAB,
    services: LAB.services.map((s) => (s.name === "orders" ? { ...s, x: 40, y: 250 } : s)),
  };
  const positions = Object.fromEntries(toNodes(moved).map((n) => [n.id, n.position]));
  expect(positions.orders).toEqual({ x: 40, y: 250 });
  expect(positions.gateway).toEqual({ x: 0, y: 0 }); // column 0, row 0
  expect(positions.inventory).toEqual({ x: 600, y: 0 }); // column 2
});
