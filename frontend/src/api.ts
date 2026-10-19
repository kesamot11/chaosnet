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

export async function fetchTopology(signal?: AbortSignal): Promise<Topology> {
  const res = await fetch("/api/topology", { signal });
  if (!res.ok) throw new Error(`GET /topology failed: HTTP ${res.status}`);
  return (await res.json()) as Topology;
}
