// Collapsible "how to read this" guide. Shown wherever a graph is rendered.
// `filterable` adds the legend-filter tip (only the global graph's legend is
// clickable).
export default function GraphHelp({ filterable = false }) {
  return (
    <details className="graph-help">
      <summary>How to read this graph</summary>
      <ul className="graph-help-body">
        <li>
          <b>Dots are memos</b>, labeled by ID and colored by department. In the{" "}
          <b>Memos + entities</b> view, the unlabeled dots are entities —{" "}
          <span className="hl" style={{ color: "#1f5fa6" }}>blue = department</span>,{" "}
          <span className="hl" style={{ color: "#2e8b57" }}>green = project</span>,{" "}
          <span className="hl" style={{ color: "#c77d11" }}>orange = person</span>.
        </li>
        <li>
          <b>Lines are relationships</b>, colored by type (see the legend). An{" "}
          <b>arrowhead</b> means direction — it points from the earlier/citing memo
          to the later/cited one.
        </li>
        <li>
          <b style={{ color: "#1f5fa6" }}>Blue, no arrow — same project.</b> The two
          memos concern the same named project. Most lines are these.
        </li>
        <li>
          <b style={{ color: "#c77d11" }}>Orange, arrow — precedes.</b> The source memo
          comes before the target in time or logic. Follow arrow chains to read a
          storyline across the quarter.
        </li>
        <li>
          <b style={{ color: "#7a4fb0" }}>Purple, arrow — references.</b> One memo
          explicitly cites another.
        </li>
        <li><b>Hover</b> a line to see the evidence behind it; hover a dot for its title.</li>
        <li><b>Click a memo</b> to open it in a new tab.</li>
        {filterable && (
          <li>
            <b>Tip:</b> click a relation type in the legend to hide it. Turn off{" "}
            <i>same_project</i> to isolate the precedes chains — the real
            cross-document structure.
          </li>
        )}
      </ul>
    </details>
  );
}
