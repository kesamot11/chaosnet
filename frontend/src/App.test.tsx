import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { App } from "./App";
import type { Experiment, Topology } from "./api";
import recorded from "./fixtures/latency-200ms.json";

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

// After a refresh (#172): the controller's answers by "METHOD path"; a Promise answers later.
// Returns, per request, the moment the UI has read the answer's body.
function serve(answers: Record<string, unknown>) {
  const read: Record<string, Promise<unknown>> = {};
  vi.stubGlobal(
    "fetch",
    vi.fn((path: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${path}`;
      if (!(key in answers)) return Promise.reject(new TypeError(`no answer for ${key}`));
      return Promise.resolve(answers[key]).then((body) => {
        const res = new Response(JSON.stringify(body), { status: 200 });
        const json = res.json.bind(res);
        res.json = () => {
          read[key] = json();
          return read[key];
        };
        return res;
      });
    }),
  );
  return read;
}

const DONE = recorded as Experiment; // completed, so the status view stops polling

test("after a refresh it follows the newest experiment", async () => {
  const newest = { ...DONE, id: 6, name: "newest" };
  serve({
    "GET /api/topology": LAB,
    "GET /api/experiments": [newest, { ...DONE, id: 5, name: "older" }],
    "GET /api/experiments/6": newest,
  });
  render(<App />);
  expect(await screen.findByRole("heading", { name: /^newest: completed/ })).toBeInTheDocument();
});

test("with no experiments yet there is no status, just the lab", async () => {
  serve({ "GET /api/topology": LAB, "GET /api/experiments": [] });
  render(<App />);
  expect(await screen.findByText(/Click a link/)).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledWith("/api/experiments", expect.anything());
  expect(screen.queryByRole("heading", { level: 2 })).not.toBeInTheDocument();
});

test("an experiment started before the list arrives is the one followed", async () => {
  let answerList: (list: Experiment[]) => void = () => {};
  const mine = { ...DONE, id: 7, name: "mine" };
  const read = serve({
    "GET /api/topology": LAB,
    "GET /api/experiments": new Promise((resolve) => {
      answerList = resolve;
    }),
    "POST /api/experiments": { id: 7, name: "mine", state: "pending", reason: null },
    "GET /api/experiments/7": mine,
  });
  render(<App />);
  const edge = await waitFor(() => {
    const e = document.querySelector('[data-id="gateway-orders"]');
    if (!e) throw new Error("the link is not drawn yet");
    return e;
  });
  fireEvent.click(edge);
  fireEvent.change(screen.getByLabelText("Name"), { target: { value: "mine" } });
  fireEvent.click(screen.getByRole("button", { name: "Start" }));
  expect(await screen.findByRole("heading", { name: /^mine: completed/ })).toBeInTheDocument();

  answerList([{ ...DONE, id: 6, name: "older" }]); // the list from before "mine" existed
  // wait until the UI has read the late list, however long that takes, and applied it
  await waitFor(() => expect(read["GET /api/experiments"]).toBeDefined());
  await act(async () => {
    await read["GET /api/experiments"];
  });
  expect(screen.getByRole("heading", { name: /^mine: completed/ })).toBeInTheDocument();
  expect(fetch).not.toHaveBeenCalledWith("/api/experiments/6", expect.anything());
});
