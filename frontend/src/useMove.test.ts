import { act, renderHook } from "@testing-library/react";
import { useState } from "react";
import { afterEach, expect, test, vi } from "vitest";
import type { Topology } from "./api";
import { useMove } from "./useMove";

const LAB: Topology = {
  version: 1,
  services: [
    { name: "gateway", port: 8080 },
    { name: "orders", port: null },
    { name: "inventory", port: null },
  ],
  links: [],
};

afterEach(() => vi.unstubAllGlobals());

/** A fake PUT /topology whose answers the test releases one at a time. */
function controller() {
  const sent: Topology[] = [];
  const answer: (() => void)[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((_: string, init: RequestInit) => {
      const body = JSON.parse(init.body as string) as Topology;
      sent.push(body);
      return new Promise<Response>((resolve) =>
        answer.push(() => resolve(new Response(JSON.stringify(body)))),
      );
    }),
  );
  return { sent, answer };
}

function render() {
  return renderHook(() => {
    const [topology, setTopology] = useState<Topology | null>(LAB);
    return { topology, ...useMove(topology, setTopology) };
  });
}

const where = (t: Topology | null, name: string) => {
  const s = t?.services.find((x) => x.name === name);
  return { x: s?.x, y: s?.y };
};

test("quick drops are saved one after another and the page keeps the last (Tomáš's review)", async () => {
  const { sent, answer } = controller();
  const { result } = render();

  act(() => result.current.move("orders", { x: 300.4, y: 62.37 }));
  act(() => result.current.move("inventory", { x: 600, y: -54.6 }));
  await act(async () => {}); // let the first save go out
  expect(sent).toHaveLength(1); // the second waits for the first
  expect(where(result.current.topology, "inventory")).toEqual({ x: 600, y: -55 });

  await act(async () => answer[0]?.()); // the first answer: orders only
  expect(where(result.current.topology, "inventory")).toEqual({ x: 600, y: -55 }); // no jump back
  expect(sent).toHaveLength(2);
  expect(where(sent[1] ?? null, "orders")).toEqual({ x: 300, y: 62 }); // the last has both

  await act(async () => answer[1]?.());
  expect(where(result.current.topology, "orders")).toEqual({ x: 300, y: 62 });
  expect(where(result.current.topology, "inventory")).toEqual({ x: 600, y: -55 });
});

test("a refused save puts the service back and says why", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(new Response(JSON.stringify({ detail: "lab busy" }), { status: 409 })),
    ),
  );
  const { result } = render();
  await act(async () => result.current.move("orders", { x: 10, y: 10 }));
  expect(where(result.current.topology, "orders")).toEqual({ x: undefined, y: undefined });
  expect(result.current.notSaved).toBe("lab busy");
});
