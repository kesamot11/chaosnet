import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import type { Topology } from "./api";
import { TopologyView } from "./TopologyView";

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
      name: "gateway-orders",
      available: false,
    },
    {
      from: "orders",
      to: "inventory",
      timeout_s: 0.5,
      max_retries: 2,
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
  render(<TopologyView topology={LAB} selected={null} onSelect={() => {}} />);
  expect(await screen.findByText("gateway :8080")).toBeInTheDocument();
  expect(screen.getByText("orders")).toBeInTheDocument();
  expect(screen.getByText("inventory")).toBeInTheDocument();
  expect(await screen.findByText("0.5 s, 2 retries")).toBeInTheDocument();
  expect(screen.getByText("no proxy")).toBeInTheDocument();
});

test("clicking an available link selects it", async () => {
  const onSelect = vi.fn();
  render(<TopologyView topology={LAB} selected={null} onSelect={onSelect} />);
  await screen.findByText("0.5 s, 2 retries");
  clickLink("orders-inventory");
  expect(onSelect).toHaveBeenCalledWith("orders-inventory");
});

test("a link without a proxy cannot be selected", async () => {
  const onSelect = vi.fn();
  render(<TopologyView topology={LAB} selected={null} onSelect={onSelect} />);
  await screen.findByText("no proxy");
  clickLink("gateway-orders");
  expect(onSelect).not.toHaveBeenCalled();
});
