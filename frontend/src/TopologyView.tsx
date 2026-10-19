import { type Edge, type Node, Position, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { Link, Topology } from "./api";
import { layout } from "./layout";

const NODE_WIDTH = 150;
const NODE_HEIGHT = 40;

type Props = {
  topology: Topology;
  selected: string | null; // name of the selected link, e.g. "orders-inventory"
  onSelect: (link: string) => void;
};

/** The lab as a graph: services are nodes, links are edges; click an edge to select it. */
export function TopologyView({ topology, selected, onSelect }: Props) {
  const positions = layout(topology);

  const nodes: Node[] = topology.services.map((service) => ({
    id: service.name,
    position: positions[service.name] ?? { x: 0, y: 0 },
    data: { label: service.port ? `${service.name} :${service.port}` : service.name },
    // Edges go left to right, so connect on the left and right side of each node.
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    // A fixed size, smaller than the gaps in layout.ts, so nodes never overlap. With the
    // size and the handles given, React Flow can draw edges without measuring the DOM.
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
    handles: [
      { type: "target", position: Position.Left, x: 0, y: NODE_HEIGHT / 2, width: 1, height: 1 },
      {
        type: "source",
        position: Position.Right,
        x: NODE_WIDTH,
        y: NODE_HEIGHT / 2,
        width: 1,
        height: 1,
      },
    ],
  }));

  const edges: Edge[] = topology.links.map((link) => ({
    id: link.name,
    source: link.from,
    target: link.to,
    label: link.available ? `${link.timeout_s} s, ${link.max_retries} retries` : "no proxy",
    selectable: link.available,
    style: edgeStyle(link, link.name === selected),
  }));

  function handleEdgeClick(link: Link | undefined) {
    // Tomáš: select the link, but only if a fault can be added to it (it is available).
    void link;
    void onSelect;
  }

  return (
    <section style={{ height: 320 }} aria-label="lab topology">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onEdgeClick={(_, edge) => handleEdgeClick(topology.links.find((l) => l.name === edge.id))}
        nodesDraggable={false}
        fitView
      />
    </section>
  );
}

function edgeStyle(link: Link, isSelected: boolean) {
  if (!link.available) return { stroke: "#999", strokeDasharray: "4 4" };
  return isSelected ? { stroke: "#d4537e", strokeWidth: 3 } : { stroke: "#555", strokeWidth: 1.5 };
}
