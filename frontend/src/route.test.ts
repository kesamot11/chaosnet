import { expect, test } from "vitest";
import { hits, route } from "./route";

// gateway, orders and inventory in one row, as layout.ts puts them (150 × 40, 300 apart)
const GATEWAY_RIGHT = { x: 150, y: 20 };
const INVENTORY_LEFT = { x: 600, y: 20 };
const ORDERS = { x: 300, y: 0, width: 150, height: 40 };

test("a link with nothing in its way keeps React Flow's curve", () => {
  const r = route(GATEWAY_RIGHT, { x: 300, y: 20 }, [{ x: 600, y: 0, width: 150, height: 40 }]);
  expect(r.path).toBe("M 150,20 C 225,20 225,20 300,20");
  expect(r.labelY).toBe(20);
});

test("a link that would cross a service arcs over it (Tomáš, #211)", () => {
  const r = route(GATEWAY_RIGHT, INVENTORY_LEFT, [ORDERS]);
  expect(r.labelY).toBeLessThan(ORDERS.y); // the top of the arc is above orders
  expect(r.labelX).toBe(375); // still in the middle
});

test("a service off the line does not bend it", () => {
  const below = { x: 300, y: 100, width: 150, height: 40 };
  expect(route(GATEWAY_RIGHT, INVENTORY_LEFT, [below]).labelY).toBe(20);
});

test("a service lying on an end of the link does not send it flying", () => {
  const onInventory = { x: 590, y: 0, width: 150, height: 40 };
  expect(route(GATEWAY_RIGHT, INVENTORY_LEFT, [onInventory]).labelY).toBe(20);
});

test("a line touches a box only where it really goes through it", () => {
  const box = { x: 0, y: 0, width: 10, height: 10 };
  expect(hits({ x: -5, y: 5 }, { x: 15, y: 5 }, box)).toBe(true); // straight through
  expect(hits({ x: -5, y: -5 }, { x: 15, y: -5 }, box)).toBe(false); // above it
  expect(hits({ x: -5, y: 30 }, { x: 30, y: -5 }, box)).toBe(false); // past a corner
  expect(hits({ x: 2, y: 2 }, { x: 3, y: 3 }, box)).toBe(true); // inside it
});
