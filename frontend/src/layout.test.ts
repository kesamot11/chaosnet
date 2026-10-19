import { expect, test } from "vitest";
import type { Topology } from "./api";
import { layout, COLUMN_GAP as X, ROW_GAP as Y } from "./layout";

/** A topology from service names and [from, to] pairs; the first service is the entry. */
function topology(services: string[], links: [string, string][]): Topology {
  return {
    version: 1,
    services: services.map((name, i) => ({ name, port: i === 0 ? 8080 : null })),
    links: links.map(([from, to]) => ({
      from,
      to,
      timeout_s: 1,
      max_retries: 0,
      name: `${from}-${to}`,
      available: true,
    })),
  };
}

test("a chain goes left to right", () => {
  const lab = topology(
    ["gateway", "orders", "inventory"],
    [
      ["gateway", "orders"],
      ["orders", "inventory"],
    ],
  );
  expect(layout(lab)).toEqual({
    gateway: { x: 0, y: 0 },
    orders: { x: X, y: 0 },
    inventory: { x: 2 * X, y: 0 },
  });
});

test("two services called by the same one share a column, in the order of services", () => {
  const lab = topology(
    ["gateway", "orders", "payments", "inventory"],
    [
      ["gateway", "orders"],
      ["orders", "inventory"],
      ["orders", "payments"],
    ],
  );
  const pos = layout(lab);
  expect(pos.payments).toEqual({ x: 2 * X, y: 0 }); // listed before inventory
  expect(pos.inventory).toEqual({ x: 2 * X, y: Y });
});

test("a service goes right of the furthest service that calls it", () => {
  // s1 -> s2 -> s4 and s1 -> s3 -> s5 -> s4: s5 is in column 2, so s4 is in column 3.
  const lab = topology(
    ["s1", "s2", "s3", "s4", "s5"],
    [
      ["s1", "s2"],
      ["s1", "s3"],
      ["s2", "s4"],
      ["s3", "s5"],
      ["s5", "s4"],
    ],
  );
  const pos = layout(lab);
  expect(pos.s5?.x).toBe(2 * X);
  expect(pos.s4?.x).toBe(3 * X);
  expect([pos.s2?.y, pos.s3?.y]).toEqual([0, Y]); // column 1, in the order of services
});

test("a service nobody calls is in the first column, below the entry", () => {
  const lab = topology(["gateway", "orders", "lonely"], [["gateway", "orders"]]);
  expect(layout(lab).lonely).toEqual({ x: 0, y: Y });
});

test("every service gets a position, and no two share one", () => {
  const lab = topology(
    ["a", "b", "c", "d"],
    [
      ["a", "b"],
      ["a", "c"],
      ["a", "d"],
    ],
  );
  const pos = Object.values(layout(lab)).map((p) => `${p.x},${p.y}`);
  expect(pos).toHaveLength(4);
  expect(new Set(pos).size).toBe(4);
});
