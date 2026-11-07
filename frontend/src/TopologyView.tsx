import {
  Background,
  BackgroundVariant,
  type Edge,
  type Node,
  Position,
  ReactFlow,
  useNodesState,
} from "@xyflow/react";
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
  service?: string | null; // the selected service (#193)
  onSelectService?: (service: string) => void;
  onConnect?: (from: string, to: string) => void; // a link drawn from a caller to a callee (#194)
  faulted?: string | null; // the link whose fault is active now, drawn in magenta (#206)
};

/**
 * The lab as a graph: services are nodes, links are edges; click an edge to select it, drag
 * from a node's right side to another's left side to draw a link.
 */
export function TopologyView({
  topology,
  selected,
  onSelect,
  onMove,
  service = null,
  onSelectService = () => {},
  onConnect = () => {},
  faulted = null,
}: Props) {
  // While a node is dragged, React Flow moves it in this state; a new topology (a save,
  // a rollback) replaces it.
  const [nodes, setNodes, onNodesChange] = useNodesState(toNodes(topology, service));
  useEffect(() => setNodes(toNodes(topology, service)), [topology, service, setNodes]);

  const edges: Edge[] = topology.links.map((link) => ({
    id: link.name,
    source: link.from,
    target: link.to,
    label: link.available ? `${link.timeout_s} s, ${link.max_retries} retries` : "no proxy",
    style: edgeStyle(link, link.name === selected, link.name === faulted),
  }));

  return (
    <section className="lab" aria-label="lab topology">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onNodeDragStop={(_, node) => onMove(node.id, node.position)}
        onNodeClick={(_, node) => onSelectService(node.id)}
        // any link, also one without a proxy: it can still be removed (Tomáš)
        onEdgeClick={(_, edge) => onSelect(edge.id)}
        onConnect={(c) => onConnect(c.source, c.target)}
        colorMode="dark"
        fitView
      >
        {/* light grey dots, evenly spread (Tomáš) */}
        <Background variant={BackgroundVariant.Dots} gap={20} size={1.5} color="#4a4b52" />
      </ReactFlow>
    </section>
  );
}

/** A node per service, where it was dropped (x, y) or else where layout.ts puts it. */
export function toNodes(topology: Topology, selected: string | null = null): Node[] {
  const positions = layout(topology);
  return topology.services.map((service) => ({
    id: service.name,
    position:
      service.x != null && service.y != null
        ? { x: service.x, y: service.y }
        : (positions[service.name] ?? { x: 0, y: 0 }),
    data: { label: service.port ? `${service.name} :${service.port}` : service.name },
    style: service.name === selected ? { borderColor: "var(--main)", borderWidth: 2 } : undefined,
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

/** Magenta only while the link's fault is active (Tomáš); violet when selected. */
function edgeStyle(link: Link, isSelected: boolean, isFaulted: boolean) {
  const dashed = link.available ? {} : { strokeDasharray: "4 4" }; // no proxy
  const stroke = isFaulted ? "var(--fault)" : isSelected ? "var(--main)" : "var(--muted)";
  return { stroke, strokeWidth: isFaulted || isSelected ? 3 : 1.5, ...dashed };
}
