/** Types and calls for the controller API (backend/src/chaosnet/api.py), via the /api proxy. */

export type Service = { name: string; port: number | null };

export type Link = {
  from: string;
  to: string;
  timeout_s: number;
  max_retries: number;
  name: string; // the Toxiproxy proxy, "<from>-<to>"
  available: boolean; // false: no proxy in Toxiproxy, so no fault can be added
};

export type Topology = { version: number; services: Service[]; links: Link[] };

export type FaultKind = "latency" | "bandwidth" | "reset_peer";
export type Direction = "request" | "response" | "both";

/** The body of POST /experiments (ExperimentSpec in backend/src/chaosnet/experiments.py). */
export type ExperimentSpec = {
  name: string;
  fault: { kind: FaultKind; link: string; direction: Direction; ms?: number; kbps?: number };
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
};

/** One point of the latency graph; null: no request was sent in that second. */
export type SecondSummary = {
  second: number;
  p50: number | null;
  p95: number | null;
  error_rate: number | null;
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
};

/** The controller's answer to a start or an abort. A refusal or no controller is an answer too. */
export type Answer = { ok: true; experiment: Experiment } | { ok: false; reason: string };

export function startExperiment(spec: ExperimentSpec): Promise<Answer> {
  return post("/api/experiments", spec);
}

export function abortExperiment(id: number): Promise<Answer> {
  return post(`/api/experiments/${id}/abort`);
}

/** One poll of #78; throws when there is no answer, the caller decides when to try again. */
export async function fetchExperiment(id: number, signal?: AbortSignal): Promise<Experiment> {
  const res = await fetch(`/api/experiments/${id}`, { signal });
  if (!res.ok) throw new Error(`GET /experiments/${id} failed: HTTP ${res.status}`);
  return (await res.json()) as Experiment;
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

/** Why the controller said no: its own message (409, unknown link) or FastAPI's field errors. */
async function refusal(res: Response): Promise<string> {
  const body: unknown = await res.json().catch(() => null); // a proxy error has no JSON body
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // loc starts with "body": ["body", "phases_s", "inject"] -> "phases_s.inject"
    return (detail as ValidationError[])
      .map((e) => `${e.loc.slice(1).join(".")}: ${e.msg}`)
      .join("; ");
  }
  return `Controller error: HTTP ${res.status}`;
}
