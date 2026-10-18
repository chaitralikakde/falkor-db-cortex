"use client";

import { useEffect, useRef } from "react";
import type { FalkorDBCanvas, GraphLink, GraphNode } from "@falkordb/canvas";
import { useDesk } from "./DeskProvider";

const PATH_COLOR = "#F5C16C";
const LINK_COLOR = "#46566b";
const SIZE: Record<string, number> = {
  Person: 15,
  System: 18,
  Project: 14,
  Decision: 13,
  Team: 14,
  Agent: 13,
  Session: 10,
  Finding: 10,
  Task: 12,
};
const DEFAULT_SIZE = 11;

/**
 * The company map. Draws whatever GET /graph returned with @falkordb/canvas,
 * dims everything that is not on the current path, and reports node clicks.
 */
export default function GraphCanvas() {
  const { graph, lit, litVersion, dim, selectNode, selectedId } = useDesk();
  const host = useRef<HTMLDivElement>(null);
  const el = useRef<FalkorDBCanvas | null>(null);
  const nodeIds = useRef<string[]>([]);
  const linkIds = useRef<string[]>([]);
  const dimRef = useRef(dim);
  const selRef = useRef<string | null>(selectedId);
  const fitted = useRef(false);
  const graphRef = useRef(graph);
  dimRef.current = dim;
  selRef.current = selectedId;
  graphRef.current = graph;

  // create the web component once
  useEffect(() => {
    let cancelled = false;
    (async () => {
      await import("@falkordb/canvas");
      if (cancelled || !host.current) return;
      const canvas = document.createElement("falkordb-canvas") as unknown as FalkorDBCanvas;
      (canvas as unknown as HTMLElement).style.cssText =
        "display:block;position:absolute;inset:0;width:100%;height:100%;overflow:hidden";
      // draw our name labels on top of the default circles
      (canvas as unknown as HTMLElement).setAttribute("node-mode", "after");
      host.current.appendChild(canvas as unknown as HTMLElement);
      el.current = canvas;

      const nodeKey = (n: GraphNode) => nodeIds.current[n.id as number];
      const linkKey = (l: GraphLink) => linkIds.current[l.id as number];
      canvas.setConfig({
        backgroundColor: "#0b0f14",
        foregroundColor: "#e6edf3",
        captionsKeys: ["name"],
        dimmed: dimRef.current,
        dimOpacity: 0.22,
        // keep node labels and arrows visible when the whole company is on screen
        largeGraph: { enabled: true, lowZoomThreshold: 0 },
        simulation: { chargeStrength: -520 },
        isNodeDimmed: (n) => dimRef.current && !lit.current.nodes.has(nodeKey(n)),
        isLinkDimmed: (l) => dimRef.current && !lit.current.links.has(linkKey(l)),
        isNodeSelected: (n) => nodeKey(n) === selRef.current,
        isLinkSelected: (l) => lit.current.links.has(linkKey(l)),
        node: {
          // the node's name under it: always when the map is plain, only on the path when it is dimmed
          nodeCanvasObject: (n, ctx) => {
            if (dimRef.current && !lit.current.nodes.has(nodeKey(n))) return;
            const full = String(n.data?.name ?? "");
            const name = full.length > 26 ? full.slice(0, 25) + "…" : full;
            const k = canvas.getZoom() || 1;
            const y = (n.y ?? 0) + n.size + 3 / k;
            ctx.save();
            ctx.font = `500 ${11 / k}px sans-serif`;
            ctx.textAlign = "center";
            ctx.textBaseline = "top";
            ctx.lineWidth = 3 / k;
            ctx.lineJoin = "round";
            ctx.strokeStyle = "#0b0f14";
            ctx.strokeText(name, n.x ?? 0, y);
            ctx.fillStyle = "#e6edf3";
            ctx.fillText(name, n.x ?? 0, y);
            ctx.restore();
          },
          nodePointerAreaPaint: (n, color, ctx) => {
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.arc(n.x ?? 0, n.y ?? 0, n.size, 0, 2 * Math.PI);
            ctx.fill();
          },
        },
        // ended ownership stays on the map, dashed
        linkLineDash: (l) => (l.data && l.data.end ? [4, 3] : []),
        eventHandlers: {
          onNodeClick: (n) => selectNode(nodeKey(n) ?? null),
          onBackgroundClick: () => selectNode(null),
          onEngineStop: () => {
            if (!fitted.current && nodeIds.current.length) {
              fitted.current = true;
              canvas.zoomToFit(1.1);
            }
          },
        },
      });
      pushData();
    })();
    return () => {
      cancelled = true;
      if (el.current) {
        (el.current as unknown as HTMLElement).remove();
        el.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const pushData = () => {
    const canvas = el.current;
    if (!canvas) return;
    const graph = graphRef.current;
    const index = new Map<string, number>();
    nodeIds.current = graph.nodes.map((n, i) => {
      index.set(n.id, i);
      return n.id;
    });
    const links = graph.links.filter((l) => index.has(l.source) && index.has(l.target));
    linkIds.current = links.map((l) => l.id);
    fitted.current = false;
    canvas.setData({
      nodes: graph.nodes.map((n, i) => ({
        id: i,
        labels: [n.label],
        color: n.color,
        visible: true,
        size: SIZE[n.label] ?? DEFAULT_SIZE,
        data: n.data,
      })),
      links: links.map((l, i) => ({
        id: i,
        relationship: l.relationship,
        color: LINK_COLOR,
        source: index.get(l.source)!,
        target: index.get(l.target)!,
        visible: true,
        data: l.data,
      })),
    });
    // fit once the layout has settled (engine stop also fits, this covers small graphs)
    setTimeout(() => canvas.zoomToFit(1.15), 900);
  };

  // new graph from the API
  useEffect(pushData, [graph]); // eslint-disable-line react-hooks/exhaustive-deps

  // dim mode on/off
  useEffect(() => {
    el.current?.setConfig({ dimmed: dim });
    el.current?.refresh();
  }, [dim]);

  // lit path or selection changed: recolor path links and repaint
  useEffect(() => {
    const canvas = el.current;
    if (!canvas) return;
    for (const l of canvas.getGraphData().links) {
      l.color = lit.current.links.has(linkIds.current[l.id as number]) ? PATH_COLOR : LINK_COLOR;
    }
    canvas.refresh();
  }, [litVersion, selectedId, lit]);

  // absolute + inset-0 gives the canvas a definite size that does not depend on its own content
  return <div ref={host} className="absolute inset-0 overflow-hidden" />;
}
