import { type Edge, type Node, Position, ReactFlow, useNodesState } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useEffect } from "react";
import type { Link, Topology } from "./api";
import { layout, type Position as Point } from "./layout";

const NODE_WIDTH = 150;
const NODE_HEIGHT = 40;

type Props = {
  topology: Topology;
  selected: string | null; // name of the selected link, e.g. "orders-inventory"
  onSelect: (link: string) => void;
  onMove: (service: string, position: Point) => void; // a service was dragged and dropped (#192)
};

/** The lab as a graph: services are nodes, links are edges; click an edge to select it. */
export function TopologyView({ topology, selected, onSelect, onMove }: Props) {
  // While a node is dragged, React Flow moves it in this state; a new topology (a save,
  // a rollback) replaces it.
  const [nodes, setNodes, onNodesChange] = useNodesState(toNodes(topology));
  useEffect(() => setNodes(toNodes(topology)), [topology, setNodes]);

  const edges: Edge[] = topology.links.map((link) => ({
    id: link.name,
    source: link.from,
    target: link.to,
    label: link.available ? `${link.timeout_s} s, ${link.max_retries} retries` : "no proxy",
    selectable: link.available,
    style: edgeStyle(link, link.name === selected),
  }));

  function handleEdgeClick(link: Link | undefined) {
    // Only a link with a proxy can take a fault.
    if (link?.available) {
      onSelect(link.name);
    }
  }

  return (
    <section style={{ height: 320 }} aria-label="lab topology">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onNodeDragStop={(_, node) => onMove(node.id, node.position)}
        onEdgeClick={(_, edge) => handleEdgeClick(topology.links.find((l) => l.name === edge.id))}
        fitView
      />
    </section>
  );
}

/** A node per service, where it was dropped (x, y) or else where layout.ts puts it. */
export function toNodes(topology: Topology): Node[] {
  const positions = layout(topology);
  return topology.services.map((service) => ({
    id: service.name,
    position:
      service.x != null && service.y != null
        ? { x: service.x, y: service.y }
        : (positions[service.name] ?? { x: 0, y: 0 }),
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
}

function edgeStyle(link: Link, isSelected: boolean) {
  if (!link.available) return { stroke: "#999", strokeDasharray: "4 4" };
  return isSelected ? { stroke: "#d4537e", strokeWidth: 3 } : { stroke: "#555", strokeWidth: 1.5 };
}
