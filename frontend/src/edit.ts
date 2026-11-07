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

/**
 * The topology with a new link from `from` to `to`, with the controller's defaults (Tomáš:
 * changed later in the link's settings). A link that is already there, or one from a service
 * to itself, would be refused only on Save, so it is refused here with why (Tomáš). A cycle
 * is left to the controller: two arrows against each other can be seen.
 */
export function addLink(topology: Topology, from: string, to: string): Topology | string {
  if (from === to) return "A service cannot call itself.";
  if (topology.links.some((l) => l.from === from && l.to === to)) {
    return "This link already exists.";
  }
  // no proxy until Save restarts the lab
  const link = { from, to, timeout_s: 1, max_retries: 0, name: `${from}-${to}`, available: false };
  return { ...topology, links: [...topology.links, link] };
}

/** The topology without the link `name`, e.g. "orders-inventory". */
export function removeLink(topology: Topology, name: string): Topology {
  return { ...topology, links: topology.links.filter((l) => l.name !== name) };
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
