import { expect, test } from "vitest";
import type { Link, Topology } from "./api";
import { addLink, addService, removeLink, removeService, withPosition } from "./edit";

const link = (from: string, to: string): Link => ({
  from,
  to,
  timeout_s: 1,
  max_retries: 0,
  name: `${from}-${to}`,
  available: true,
});

const LAB: Topology = {
  version: 1,
  services: [
    { name: "gateway", port: 8080 },
    { name: "orders", port: null },
    { name: "inventory", port: null },
  ],
  links: [link("gateway", "orders"), link("orders", "inventory"), link("gateway", "inventory")],
};

test("a new service has no port, unless the lab is empty: then it is the entry (Tomáš)", () => {
  expect(addService(LAB, "payments").services.at(-1)).toEqual({ name: "payments", port: null });
  const empty: Topology = { ...LAB, services: [], links: [] };
  expect(addService(empty, "shop").services).toEqual([{ name: "shop", port: 8080 }]);
});

test("removing a service removes its links to it and from it, and no other (Tomáš)", () => {
  const without = removeService(LAB, "orders");
  expect(without.services.map((s) => s.name)).toEqual(["gateway", "inventory"]);
  expect(without.links.map((l) => l.name)).toEqual(["gateway-inventory"]);
  expect(LAB.links).toHaveLength(3); // the saved topology is not changed
});

test("a position is kept in whole pixels", () => {
  const moved = withPosition(LAB, "orders", { x: 300.4, y: 62.6 });
  expect(moved.services[1]).toEqual({ name: "orders", port: null, x: 300, y: 63 });
});

test("a new link gets the controller's defaults and no proxy until Save (Tomáš)", () => {
  const added = addLink(LAB, "inventory", "orders");
  if (typeof added === "string") throw new Error(added);
  expect(added.links.at(-1)).toEqual({
    from: "inventory",
    to: "orders",
    timeout_s: 1,
    max_retries: 0,
    name: "inventory-orders",
    available: false,
  });
});

test("a link that is there already, or to the service itself, is not added (Tomáš)", () => {
  expect(addLink(LAB, "gateway", "orders")).toBe("This link already exists.");
  expect(addLink(LAB, "orders", "orders")).toBe("A service cannot call itself.");
});

test("a cycle is added: the controller refuses it on Save, and it can be seen", () => {
  expect(addLink(LAB, "inventory", "gateway")).not.toBeTypeOf("string");
});

test("removing a link removes that one only", () => {
  expect(removeLink(LAB, "orders-inventory").links.map((l) => l.name)).toEqual([
    "gateway-orders",
    "gateway-inventory",
  ]);
});
