import { useEffect } from "react";
import ResponseGraph from "./ResponseGraph.jsx";

// Pop-out overlay around the per-response evidence graph. `extracted` is a
// query_b `extracted_data` object; memo nodes are derived from its fields.
export default function GraphModal({ extracted, memoIds, onClose }) {
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="graph-overlay" onClick={onClose}>
      <div className="graph-modal" onClick={(e) => e.stopPropagation()}>
        <div className="graph-modal-head">
          <h3>Evidence graph</h3>
          <button className="graph-close" onClick={onClose}>✕</button>
        </div>
        <ResponseGraph extracted={extracted} memoIds={memoIds} />
      </div>
    </div>
  );
}
