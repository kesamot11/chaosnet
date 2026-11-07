/** Types and calls for the controller API (backend/src/chaosnet/api.py), via the /api proxy. */

// Jaeger's UI, published by the lab on this port (#157); a trace opens at /trace/<id>.
export const JAEGER = "http://127.0.0.1:16686";

export type Service = {
  name: string;
  port: number | null;
  // Where the editor draws it (#192); null or missing: placed by layout.ts.
  x?: number | null;
  y?: number | null;
};

/** What a link does when its callee is slow or fails (Link in backend/src/chaosnet/topology.py). */
export type LinkSettings = {
  from: string;
  to: string;
  timeout_s: number;
  max_retries: number;
  backoff_s: number;
  breaker: boolean;
  retry_budget: number | null; // null: no budget
  fallback: boolean;
};

export type Link = LinkSettings & {
  name: string; // the Toxiproxy proxy, "<from>-<to>"
  available: boolean; // false: no proxy in Toxiproxy, so no fault can be added
};

export type Topology = { version: number; services: Service[]; links: Link[] };

export type FaultKind = "latency" | "bandwidth" | "reset_peer";
export type Direction = "request" | "response" | "both";

/** The body of POST /experiments (ExperimentSpec in backend/src/chaosnet/experiments.py). */
export type ExperimentSpec = {
  name: string;
  fault: {
    kind: FaultKind;
    link: string;
    direction: Direction;
    ms?: number | null;
    kbps?: number | null;
  };
  load: { rate: number; body: Record<string, unknown> };
  phases_s: { baseline: number; inject: number; recover: number };
  hypothesis: { max_p95_ms: number; max_error_rate: number };
};

export async function fetchTopology(signal?: AbortSignal): Promise<Topology> {
  const res = await fetch("/api/topology", { signal });
  if (!res.ok) throw new Error(`GET /topology failed: HTTP ${res.status}`);
  return (await res.json()) as Topology;
}

export type State =
  | "pending"
  | "baseline"
  | "inject"
  | "recover"
  | "completed"
  | "failed"
  | "aborted";
export type Phase = "baseline" | "inject" | "recover";

/** No way out of these (TRANSITIONS in backend/src/chaosnet/experiments.py). */
export const END_STATES: ReadonlySet<State> = new Set(["completed", "failed", "aborted"]);

type Percentiles = { p50: number; p95: number; p99: number; p100: number };

/** What the load generator measured in one phase (summarize in backend/src/chaosnet/loadgen.py). */
export type PhaseSummary = {
  scheduled: number;
  outcomes: Record<string, number>; // e.g. { ok: 150, timeout: 50 }; a key with 0 is missing
  latency_ms: { ok: Percentiles | null; all: Percentiles | null }; // null: no requests
  per_second: SecondSummary[]; // from second 0 to the last second with a request (#62)
  // The trace to open for this phase (#159); missing in experiments recorded before it.
  example_trace?: string | null;
};

/** One point of the latency graph; null: no request was sent in that second. */
export type SecondSummary = {
  second: number;
  p50: number | null;
  p95: number | null;
  error_rate: number | null;
  trace?: string | null; // the request to open in Jaeger (#173); missing before it
};

/** The record of one experiment (Experiment in backend/src/chaosnet/store.py), the fields the UI reads. */
export type Experiment = {
  id: number;
  name: string;
  state: State;
  spec: ExperimentSpec;
  results: Partial<Record<Phase, PhaseSummary>>; // a phase appears when it has been measured
  verdict: { passed: boolean; reasons: string[] } | null; // null until completed
  reason: string | null; // why it failed or was aborted
  // The lab it ran on (#185); null for experiments from before it was recorded.
  topology?: { links: LinkSettings[] } | null;
};

/** The controller's answer to a start or an abort. A refusal or no controller is an answer too. */
export type Answer = { ok: true; experiment: Experiment } | { ok: false; reason: string };

export function startExperiment(spec: ExperimentSpec): Promise<Answer> {
  return post("/api/experiments", spec);
}

export function abortExperiment(id: number): Promise<Answer> {
  return post(`/api/experiments/${id}/abort`);
}

/** Every experiment, newest first (#172). */
export async function fetchExperiments(signal?: AbortSignal): Promise<Experiment[]> {
  const res = await fetch(`/api/experiments`, { signal });
  if (!res.ok) throw new Error(`GET /experiments failed: HTTP ${res.status}`);
  return (await res.json()) as Experiment[];
}

/** One poll of #78; throws when there is no answer, the caller decides when to try again. */
export async function fetchExperiment(id: number, signal?: AbortSignal): Promise<Experiment> {
  const res = await fetch(`/api/experiments/${id}`, { signal });
  if (!res.ok) throw new Error(`GET /experiments/${id} failed: HTTP ${res.status}`);
  return (await res.json()) as Experiment;
}

/** The controller's answer to a save: the topology as saved, or why not (#190, #192). */
export type Saved = { ok: true; topology: Topology } | { ok: false; reason: string };

/** Save a topology; a change of the lab is then applied in the background (GET /lab). */
export async function saveTopology(topology: Topology): Promise<Saved> {
  let res: Response;
  try {
    res = await fetch("/api/topology", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(topology),
    });
  } catch (e) {
    return { ok: false, reason: `Controller not reachable: ${e instanceof Error ? e.message : e}` };
  }
  if (res.ok) return { ok: true, topology: (await res.json()) as Topology };
  return { ok: false, reason: await refusal(res, topology) };
}

export type LabState = "running" | "restarting" | "failed";
/** GET /lab (#191): whether the lab runs; `error` also when running after a rollback. */
export type LabStatus = { state: LabState; error: string | null };

export async function fetchLab(signal?: AbortSignal): Promise<LabStatus> {
  const res = await fetch("/api/lab", { signal });
  if (!res.ok) throw new Error(`GET /lab failed: HTTP ${res.status}`);
  return (await res.json()) as LabStatus;
}

async function post(path: string, body?: unknown): Promise<Answer> {
  let res: Response;
  try {
    res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (e) {
    return { ok: false, reason: `Controller not reachable: ${e instanceof Error ? e.message : e}` };
  }
  if (res.ok) return { ok: true, experiment: (await res.json()) as Experiment };
  return { ok: false, reason: await refusal(res) };
}

type ValidationError = { loc: (string | number)[]; msg: string };

/**
 * Why the controller said no: its own message (409, unknown link) or FastAPI's field errors.
 * With the topology that was sent, a link or service is named, not numbered (Tomáš, #185).
 */
async function refusal(res: Response, sent?: Topology): Promise<string> {
  const body: unknown = await res.json().catch(() => null); // a proxy error has no JSON body
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // loc starts with "body": ["body", "phases_s", "inject"] -> "phases_s.inject"; a rule of
    // the whole body (check, #190) has only "body", and Pydantic's prefix says nothing
    return (detail as ValidationError[])
      .map((e) => {
        const where = place(e.loc.slice(1), sent);
        const msg = e.msg.replace(/^Value error, /, "");
        return where === "" ? msg : `${where}: ${msg}`;
      })
      .join("; ");
  }
  return `Controller error: HTTP ${res.status}`;
}

/** ["links", 1, "timeout_s"] -> "orders-inventory: timeout_s", given what was sent; else "links.1.timeout_s". */
function place(path: (string | number)[], sent?: Topology): string {
  const [list, i, ...rest] = path;
  const item =
    (list === "links" || list === "services") && typeof i === "number"
      ? sent?.[list][i]
      : undefined;
  if (item === undefined) return path.join(".");
  return rest.length === 0 ? item.name : `${item.name}: ${rest.join(".")}`;
}
