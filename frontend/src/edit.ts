import type { Topology } from "./api";

export const ENTRY_PORT = 8080; // as gateway's in lab/topology.json

/**
 * A new service, drawn by layout.ts until it is moved; the controller checks its name (422).
 * Only the entry has a port (check), so it gets one only in an empty lab (Tomáš).
 */
export function addService(topology: Topology, name: string): Topology {
  const port = topology.services.length === 0 ? ENTRY_PORT : null;
  return { ...topology, services: [...topology.services, { name, port }] };
}

/** The topology without `name` and without its links, to it and from it (Tomáš). */
export function removeService(topology: Topology, name: string): Topology {
  return {
    ...topology,
    services: topology.services.filter((s) => s.name !== name),
    links: topology.links.filter((l) => l.from !== name && l.to !== name),
  };
}

/** The topology with `service` drawn at `position`, in whole pixels (#192). */
export function withPosition(
  topology: Topology,
  service: string,
  position: { x: number; y: number },
): Topology {
  const at = { x: Math.round(position.x), y: Math.round(position.y) }; // a readable file
  return {
    ...topology,
    services: topology.services.map((s) => (s.name === service ? { ...s, ...at } : s)),
  };
}
