import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { App, LabLine } from "./App";
import type { Experiment, LabStatus, Topology } from "./api";
import recorded from "./fixtures/latency-200ms.json";
import { POLL_MS } from "./useExperiment";

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
  // one Response per request: a body can be read only once
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(JSON.stringify(LAB)))),
  );
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

test("what the user is told about the lab, in each state (#192)", () => {
  const cases: [LabStatus, string][] = [
    [{ state: "restarting", error: null }, "The lab is restarting, hold on a moment…"],
    [
      { state: "failed", error: "port is already allocated" },
      "The lab failed: port is already allocated",
    ],
    [
      { state: "running", error: "container payments is unhealthy" },
      "The last change failed, so the previous lab is back: container payments is unhealthy",
    ],
    [{ state: "running", error: null }, "The lab is running."],
  ];
  for (const [lab, text] of cases) {
    const { container, unmount } = render(<LabLine lab={lab} />);
    expect(container.textContent).toBe(text);
    unmount();
  }
});

test("when a restart ends, the topology is loaded again: it may have been rolled back", async () => {
  const states: LabStatus[] = [
    { state: "running", error: null },
    { state: "restarting", error: null },
    { state: "restarting", error: null },
    { state: "running", error: "container payments is unhealthy" },
  ];
  let topologyRequests = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn((path: string) => {
      if (path === "/api/topology") topologyRequests++;
      const body =
        path === "/api/lab"
          ? (states.shift() ?? states.at(-1))
          : path === "/api/experiments"
            ? []
            : LAB;
      return Promise.resolve(new Response(JSON.stringify(body)));
    }),
  );
  vi.useFakeTimers({ shouldAdvanceTime: true });
  try {
    render(<App />);
    expect(await screen.findByText("The lab is running.")).toBeInTheDocument();
    expect(topologyRequests).toBe(1); // the page's own load
    await vi.advanceTimersByTimeAsync(POLL_MS); // restarting
    await vi.advanceTimersByTimeAsync(POLL_MS); // still restarting: no reload yet
    expect(screen.getByText(/restarting/)).toBeInTheDocument();
    expect(topologyRequests).toBe(1);
    await vi.advanceTimersByTimeAsync(POLL_MS); // ended, rolled back
    expect(await screen.findByRole("alert")).toHaveTextContent("previous lab is back");
    expect(topologyRequests).toBe(2);
  } finally {
    vi.useRealTimers();
  }
});

test("services are added and removed in a draft, applied only by Save (#193)", async () => {
  const puts: Topology[] = [];
  const reply = (body: unknown, status = 200) =>
    Promise.resolve(new Response(JSON.stringify(body), { status }));
  vi.stubGlobal(
    "fetch",
    vi.fn((path: string, init?: RequestInit) => {
      if (init?.method === "PUT") {
        const sent = JSON.parse(init.body as string) as Topology;
        puts.push(sent);
        if (sent.services.some((s) => s.name === "Pay Ments")) {
          const msg = "Value error, wrong syntax for service with name 'Pay Ments'";
          return reply({ detail: [{ loc: ["body"], msg }] }, 422);
        }
        return reply(sent);
      }
      if (path === "/api/lab") return reply({ state: "running", error: null });
      if (path === "/api/experiments") return reply([]);
      return reply(LAB);
    }),
  );
  render(<App />);
  const save = await screen.findByRole("button", { name: "Save" });
  expect(save).toBeDisabled(); // nothing to save yet

  fireEvent.change(screen.getByLabelText("New service"), { target: { value: "Pay Ments" } });
  fireEvent.click(screen.getByRole("button", { name: "Add" }));
  expect(await screen.findByText("Pay Ments")).toBeInTheDocument(); // drawn from the draft
  expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
  expect(puts).toHaveLength(0); // not sent before Save

  fireEvent.click(save);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    /^Not saved: wrong syntax for service with name 'Pay Ments'$/,
  );
  expect(screen.getByText("Pay Ments")).toBeInTheDocument(); // the draft is kept to fix

  // select orders and remove it: its link to gateway goes with it
  const orders = document.querySelector('.react-flow__node[data-id="orders"]');
  if (!orders) throw new Error("orders is not drawn");
  fireEvent.click(orders);
  fireEvent.click(screen.getByRole("button", { name: "Remove orders" }));
  expect(screen.queryByText("orders")).not.toBeInTheDocument();
  const payments = document.querySelector('.react-flow__node[data-id="Pay Ments"]');
  if (!payments) throw new Error("Pay Ments is not drawn");
  fireEvent.click(payments);
  fireEvent.click(screen.getByRole("button", { name: "Remove Pay Ments" }));

  fireEvent.click(save);
  await waitFor(() => expect(screen.queryByText("Unsaved changes")).not.toBeInTheDocument());
  expect(puts.at(-1)?.services.map((s) => s.name)).toEqual(["gateway"]);
  expect(puts.at(-1)?.links).toEqual([]); // gateway-orders went with orders
});

test("a link without a proxy has no fault form, and Remove takes it out of the draft", async () => {
  const lab: Topology = { ...LAB, links: LAB.links.map((l) => ({ ...l, available: false })) };
  const puts: Topology[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((path: string, init?: RequestInit) => {
      if (init?.method === "PUT") puts.push(JSON.parse(String(init.body)));
      const body =
        path === "/api/lab"
          ? { state: "running", error: null }
          : path === "/api/experiments"
            ? []
            : (puts.at(-1) ?? lab);
      return Promise.resolve(new Response(JSON.stringify(body)));
    }),
  );
  render(<App />);
  const edge = await waitFor(() => {
    const e = document.querySelector('[data-id="gateway-orders"]');
    if (!e) throw new Error("the link is not drawn yet");
    return e;
  });
  fireEvent.click(edge);
  expect(screen.getByText("Save the lab, then you can add a fault here.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /start/i })).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Remove link gateway-orders" }));
  expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(puts).toHaveLength(1));
  expect(puts.at(-1)?.links).toEqual([]);
});

test("one thing is selected at a time, and never one that is gone (Tomáš's review)", async () => {
  let lab: Topology = LAB;
  const states: LabStatus[] = [{ state: "running", error: null }];
  vi.stubGlobal(
    "fetch",
    vi.fn((path: string) => {
      const body =
        path === "/api/lab"
          ? (states.shift() ?? { state: "running", error: null })
          : path === "/api/experiments"
            ? []
            : lab;
      return Promise.resolve(new Response(JSON.stringify(body)));
    }),
  );
  vi.useFakeTimers({ shouldAdvanceTime: true });
  try {
    render(<App />);
    const edge = await waitFor(() => {
      const e = document.querySelector('[data-id="gateway-orders"]');
      if (!e) throw new Error("the link is not drawn yet");
      return e;
    });
    fireEvent.click(edge);
    expect(screen.getByText("Selected link: gateway-orders")).toBeInTheDocument();

    const orders = document.querySelector('.react-flow__node[data-id="orders"]');
    if (!orders) throw new Error("orders is not drawn");
    fireEvent.click(orders);
    expect(screen.getByRole("button", { name: "Remove orders" })).toBeInTheDocument();
    expect(screen.queryByText(/Selected link/)).not.toBeInTheDocument(); // the link is not

    // a restart that ends without orders (a rollback): its selection goes with it
    lab = { ...LAB, services: LAB.services.filter((s) => s.name !== "orders"), links: [] };
    states.push({ state: "restarting", error: null }, { state: "running", error: "rolled back" });
    await vi.advanceTimersByTimeAsync(POLL_MS);
    await vi.advanceTimersByTimeAsync(POLL_MS);
    await waitFor(() => expect(screen.queryByText("orders")).not.toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Remove orders" })).not.toBeInTheDocument();
  } finally {
    vi.useRealTimers();
  }
});
