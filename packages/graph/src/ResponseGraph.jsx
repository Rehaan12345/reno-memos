import { useMemo, useState } from "react";
import GraphCanvas, { colorFor, REL_COLORS, DIRECTED } from "./GraphCanvas.jsx";
import GraphHelp from "./GraphHelp.jsx";

const ENTITY_COLORS = {
  departments: "#1f5fa6",
  projects: "#2e8b57",
  people: "#c77d11",
};
const APPEARS_IN = "#cdd4df"; // faint edge: entity appears in a memo

// Build {nodes, links} for one B-research response. "memos" mode shows only the
// retrieved memos joined by typed relationship edges; "bipartite" mode adds the
// entities (departments/projects/people) as nodes linked to the memos they
// appear in.
function buildGraph(extracted, memoIds, mode) {
  const ids = new Set(memoIds);
  const fields = extracted.fields || {};

  const nodes = memoIds.map((id) => ({
    id,
    kind: "memo",
    label: id,
    title: fields[id]?.title || id,
    group: fields[id]?.department || "Unknown",
  }));

  // query_b returns edges touching ANY used memo; keep only edges whose both
  // endpoints are in the retrieved set so there are no dangling targets.
  const links = (extracted.relationships || [])
    .filter((r) => ids.has(r.source_id) && ids.has(r.target_id))
    .map((r) => ({
      source: r.source_id,
      target: r.target_id,
      rel_type: r.rel_type,
      evidence: r.evidence,
    }));

  if (mode === "bipartite") {
    for (const e of extracted.entities || []) {
      const eid = `${e.type}:${e.name}`;
      nodes.push({ id: eid, kind: "entity", etype: e.type, title: `${e.name} · ${e.type}` });
      for (const m of e.memo_ids || []) {
        if (ids.has(m)) links.push({ source: eid, target: m, rel_type: "appears_in" });
      }
    }
  }
  return { nodes, links };
}

// `memoIds` defaults to the keys of extracted.fields, which are exactly the
// retrieved memos — so callers that only have extracted_data can omit it.
export default function ResponseGraph({ extracted = {}, memoIds, nodeHref }) {
  const ids = memoIds || Object.keys(extracted.fields || {});
  const [mode, setMode] = useState("memos");
  const graphData = useMemo(() => buildGraph(extracted, ids, mode), [extracted, ids, mode]);

  if (graphData.nodes.length === 0) {
    return <p className="status-msg">No memos were retrieved, so there is nothing to graph.</p>;
  }

  const relTypes = [
    ...new Set(graphData.links.filter((l) => l.rel_type !== "appears_in").map((l) => l.rel_type)),
  ];

  return (
    <div className="response-graph">
      <div className="graph-toolbar">
        <div className="seg">
          <button className={mode === "memos" ? "on" : ""} onClick={() => setMode("memos")}>
            Memos
          </button>
          <button className={mode === "bipartite" ? "on" : ""} onClick={() => setMode("bipartite")}>
            Memos + entities
          </button>
        </div>
        <div className="graph-legend">
          {relTypes.map((t) => (
            <span key={t} className="legend-item">
              <i style={{ background: REL_COLORS[t] || "#999" }} /> {t}
            </span>
          ))}
          {mode === "bipartite" &&
            Object.entries(ENTITY_COLORS).map(([t, c]) => (
              <span key={t} className="legend-item">
                <i className="dot" style={{ background: c }} /> {t}
              </span>
            ))}
        </div>
      </div>
      <GraphHelp />
      <GraphCanvas
        graphData={graphData}
        nodeColor={(n) => (n.kind === "entity" ? ENTITY_COLORS[n.etype] || "#999" : colorFor(n.group))}
        nodeLabel={(n) => n.title}
        drawLabel={(n) => (n.kind === "memo" ? n.label : null)}
        linkColor={(l) => (l.rel_type === "appears_in" ? APPEARS_IN : REL_COLORS[l.rel_type] || "#999")}
        linkLabel={(l) => l.evidence || l.rel_type}
        isDirected={(l) => DIRECTED.has(l.rel_type)}
        nodeHref={nodeHref}
      />
    </div>
  );
}
