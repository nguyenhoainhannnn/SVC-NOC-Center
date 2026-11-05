import dagre from "dagre";
import { Edge, Node, Position } from "@xyflow/react";
import { NocEdgeData, NocNodeData, PathHop } from "./types";

const NODE_DIMENSIONS: Record<string, { width: number; height: number }> = {
  routerNode: { width: 290, height: 185 },
  switchNode: { width: 350, height: 225 },
  unmanagedGroupNode: { width: 300, height: 190 },
  endpointNode: { width: 235, height: 84 },
};

export function applyDagreLayout(
  nodes: Node<NocNodeData>[],
  edges: Edge<NocEdgeData>[],
  direction: "LR" | "TB" = "LR"
): Node<NocNodeData>[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({
    rankdir: direction,
    nodesep: 36,
    ranksep: 130,
    marginx: 40,
    marginy: 40,
  });

  nodes.forEach((node) => {
    const dim = NODE_DIMENSIONS[node.type || "endpointNode"] || { width: 240, height: 100 };
    g.setNode(node.id, { width: dim.width, height: dim.height });
  });

  edges.forEach((edge) => {
    g.setEdge(edge.source, edge.target);
  });

  dagre.layout(g);

  return nodes.map((node) => {
    const pos = g.node(node.id);
    const dim = NODE_DIMENSIONS[node.type || "endpointNode"] || { width: 240, height: 100 };
    return {
      ...node,
      sourcePosition: direction === "LR" ? Position.Right : Position.Bottom,
      targetPosition: direction === "LR" ? Position.Left : Position.Top,
      position: pos
        ? { x: pos.x - dim.width / 2, y: pos.y - dim.height / 2 }
        : node.position,
    };
  });
}

export interface UpstreamHighlightResult {
  activeNodeIds: Set<string>;
  activeEdgeIds: Set<string>;
  switchPortsByNodeId: Record<string, number[]>;
  hops: PathHop[];
}

/**
 * Traverse the topology graph upstream from `startNodeId` all the way to the Root Router.
 */
export function traceUpstreamPath(
  startNodeId: string | null,
  nodes: Node<NocNodeData>[],
  edges: Edge<NocEdgeData>[]
): UpstreamHighlightResult {
  const activeNodeIds = new Set<string>();
  const activeEdgeIds = new Set<string>();
  const switchPortsByNodeId: Record<string, number[]> = {};
  const hops: PathHop[] = [];

  if (!startNodeId) {
    return { activeNodeIds, activeEdgeIds, switchPortsByNodeId, hops };
  }

  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  const incomingByTarget = new Map<string, Edge<NocEdgeData>[]>();
  edges.forEach((e) => {
    const list = incomingByTarget.get(e.target) || [];
    list.push(e);
    incomingByTarget.set(e.target, list);
  });

  const addSwitchPort = (nodeId: string, port?: number) => {
    if (!port || port <= 0) return;
    if (!switchPortsByNodeId[nodeId]) switchPortsByNodeId[nodeId] = [];
    if (!switchPortsByNodeId[nodeId].includes(port)) {
      switchPortsByNodeId[nodeId].push(port);
    }
  };

  const queue: string[] = [startNodeId];
  activeNodeIds.add(startNodeId);

  while (queue.length > 0) {
    const currentId = queue.shift()!;
    const incomingEdges = incomingByTarget.get(currentId) || [];

    for (const edge of incomingEdges) {
      activeEdgeIds.add(edge.id);
      const srcPort = edge.data?.source_port;
      const dstPort = edge.data?.target_port;
      addSwitchPort(edge.source, srcPort);
      addSwitchPort(edge.target, dstPort);

      const srcNode = nodeMap.get(edge.source);
      const dstNode = nodeMap.get(edge.target);
      hops.push({
        fromNodeId: edge.source,
        fromNodeName: srcNode?.data?.name || srcNode?.data?.label || edge.source,
        fromPort: srcPort,
        toNodeId: edge.target,
        toNodeName: dstNode?.data?.name || dstNode?.data?.label || edge.target,
        toPort: dstPort,
        linkType: edge.data?.link_type || "access",
        speed: edge.data?.speed || "1G",
      });

      if (!activeNodeIds.has(edge.source)) {
        activeNodeIds.add(edge.source);
        queue.push(edge.source);
      }
    }
  }

  return { activeNodeIds, activeEdgeIds, switchPortsByNodeId, hops };
}
