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

/** The record of one experiment (Experiment in backend/src/chaosnet/store.py), the fields the UI reads. */
export type Experiment = { id: number; name: string; state: string; reason: string | null };

export type StartResult = { ok: true; experiment: Experiment } | { ok: false; reason: string };

/** Start an experiment. A refusal or a missing controller is a result, not an exception. */
export async function startExperiment(spec: ExperimentSpec): Promise<StartResult> {
  let res: Response;
  try {
    res = await fetch("/api/experiments", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(spec),
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
