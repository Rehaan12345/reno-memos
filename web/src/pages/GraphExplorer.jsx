import { useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import { GraphCanvas, GraphHelp, colorFor, REL_COLORS, DIRECTED } from "@reno/graph";

// The full B-research relationship graph: every memo and every typed edge from
// reno_b.db. 75% of edges are same_project, so a per-type filter lets you
// isolate the directed precedes chains.
export default function GraphExplorer() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [hidden, setHidden] = useState(() => new Set());

  useEffect(() => {
    api.researchGraph().then(setData).catch((e) => setError(e.message));
  }, []);

  const relTypes = useMemo(
    () => (data ? [...new Set(data.links.map((l) => l.rel_type))].sort() : []),
    [data],
  );
  // Keep node objects stable across filter changes so the layout doesn't reset.
  const nodes = useMemo(() => (data ? data.nodes.map((n) => ({ ...n })) : []), [data]);
  const graphData = useMemo(
    () => ({
      nodes,
      links: data ? data.links.filter((l) => !hidden.has(l.rel_type)).map((l) => ({ ...l })) : [],
    }),
    [nodes, data, hidden],
  );

  function toggle(t) {
    setHidden((prev) => {
      const next = new Set(prev);
      next.has(t) ? next.delete(t) : next.add(t);
      return next;
    });
  }

  if (error) return <p className="status-msg error">Error: {error}</p>;
  if (!data) return <p className="status-msg">Loading graph…</p>;

  return (
    <div className="graph-explorer">
      <div className="result-head">
        <h1>Relationship graph</h1>
        <span className="memo-meta">
          {data.nodes.length} memos · {data.links.length} edges
        </span>
      </div>
      <div className="graph-toolbar">
        <div className="graph-legend">
          {relTypes.map((t) => (
            <button
              key={t}
              className={`legend-item toggle${hidden.has(t) ? " off" : ""}`}
              onClick={() => toggle(t)}
            >
              <i style={{ background: REL_COLORS[t] || "#999" }} /> {t}
            </button>
          ))}
        </div>
      </div>
      <GraphHelp filterable />
      <GraphCanvas
        graphData={graphData}
        nodeColor={(n) => colorFor(n.department)}
        nodeLabel={(n) => `${n.id} · ${n.title}`}
        drawLabel={(n) => n.id}
        linkColor={(l) => REL_COLORS[l.rel_type] || "#999"}
        linkLabel={(l) => l.evidence || l.rel_type}
        isDirected={(l) => DIRECTED.has(l.rel_type)}
      />
    </div>
  );
}
