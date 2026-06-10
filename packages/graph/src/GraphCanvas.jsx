import { useEffect, useRef, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";

// Stable palette + deterministic hash so the same department always gets the
// same color across renders and across the two graph views.
const PALETTE = [
  "#1f5fa6", "#2e8b57", "#c77d11", "#7a4fb0",
  "#b0573f", "#0f8b8d", "#c0392b", "#5b6678",
];
export function colorFor(key) {
  let h = 0;
  for (let i = 0; i < (key || "").length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
  return PALETTE[h % PALETTE.length];
}

// Color per approved relation type (from CLAUDE.md's bounded vocabulary).
export const REL_COLORS = {
  same_project: "#1f5fa6",
  precedes: "#c77d11",
  references: "#7a4fb0",
  funds: "#2e8b57",
  authorizes: "#0f8b8d",
  depends_on: "#b0573f",
  assigned_to: "#5b6678",
  conflicts_with: "#c0392b",
};
// Relation types that carry a source -> target direction (draw an arrowhead).
export const DIRECTED = new Set([
  "precedes", "references", "funds", "authorizes", "depends_on", "assigned_to",
]);

// Presentational force-directed graph. Measures its container (sized by CSS) so
// the canvas fills the space; all node/link styling is driven by callback props
// so every view can reuse it.
export default function GraphCanvas({
  graphData,
  nodeColor,
  nodeLabel,
  drawLabel,
  linkColor,
  linkLabel,
  isDirected,
  nodeHref,
  className = "graph-canvas",
}) {
  const wrapRef = useRef(null);
  const [size, setSize] = useState({ w: 0, h: 0 });

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const r = entries[0].contentRect;
      setSize({ w: r.width, h: r.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return (
    <div className={className} ref={wrapRef}>
      {size.w > 0 && size.h > 0 && (
        <ForceGraph2D
          width={size.w}
          height={size.h}
          graphData={graphData}
          backgroundColor="#ffffff"
          nodeColor={nodeColor}
          nodeLabel={nodeLabel}
          nodeRelSize={5}
          onNodeClick={(node) => {
            const href = nodeHref?.(node);
            if (href) window.open(href, "_blank", "noopener,noreferrer");
          }}
          onNodeHover={(node) => {
            if (wrapRef.current) {
              wrapRef.current.style.cursor = node && nodeHref?.(node) ? "pointer" : "default";
            }
          }}
          nodeCanvasObjectMode={() => "after"}
          nodeCanvasObject={(node, ctx, scale) => {
            const label = drawLabel?.(node);
            if (!label) return;
            const fontSize = 11 / scale;
            ctx.font = `${fontSize}px -apple-system, sans-serif`;
            ctx.textAlign = "center";
            ctx.textBaseline = "top";
            ctx.fillStyle = "#1a2230";
            ctx.fillText(label, node.x, node.y + 7);
          }}
          linkColor={linkColor}
          linkLabel={linkLabel}
          linkWidth={1.2}
          linkDirectionalArrowLength={(l) => (isDirected?.(l) ? 4 : 0)}
          linkDirectionalArrowRelPos={1}
          cooldownTicks={120}
        />
      )}
    </div>
  );
}
