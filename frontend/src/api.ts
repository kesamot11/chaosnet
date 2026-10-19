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
