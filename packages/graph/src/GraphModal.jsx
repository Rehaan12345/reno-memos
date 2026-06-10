import { useEffect, useMemo } from "react";
import ResponseGraph from "./ResponseGraph.jsx";

// Pop-out overlay around the per-response evidence graph. `extracted` is a
// query_b `extracted_data` object; memo nodes are derived from its fields.
// `sources` is the response's cited_sources; clicking a memo opens its
// published PDF in a new tab.
export default function GraphModal({ extracted, memoIds, sources, onClose }) {
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const srcByMemo = useMemo(
    () => Object.fromEntries((sources || []).map((s) => [s.memo_id, s.source_url])),
    [sources],
  );
  const nodeHref = (n) => (n.kind === "memo" ? srcByMemo[n.id] : null);

  return (
    <div className="graph-overlay" onClick={onClose}>
      <div className="graph-modal" onClick={(e) => e.stopPropagation()}>
        <div className="graph-modal-head">
          <h3>Evidence graph</h3>
          <button className="graph-close" onClick={onClose}>✕</button>
        </div>
        <ResponseGraph extracted={extracted} memoIds={memoIds} nodeHref={nodeHref} />
      </div>
    </div>
  );
}
