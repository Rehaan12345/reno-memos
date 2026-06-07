import { useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { loadHistory, clearHistory } from "../history.js";
import Result from "../components/Result.jsx";

const ROUTE_LABELS = {
  reasoning: "Synthesis",
  threads: "Thread",
  flags: "Flags",
  metrics: "Metric",
};

function when(ts) {
  const d = new Date(ts);
  return d.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export default function History() {
  const [entries, setEntries] = useState(loadHistory);
  const [params, setParams] = useSearchParams();
  const selectedId = params.get("id");
  const selected = entries.find((e) => e.id === selectedId);

  function clearAll() {
    clearHistory();
    setEntries([]);
    setParams({});
  }

  if (entries.length === 0) {
    return (
      <div className="browse">
        <header className="browse-head">
          <h1>Chat history</h1>
          <p className="lede">No questions yet.</p>
        </header>
        <Link to="/" className="chip">
          Ask a question
        </Link>
      </div>
    );
  }

  return (
    <div className="history">
      <aside className="history-list">
        <div className="history-list-head">
          <h2>History</h2>
          <button className="link-btn" onClick={clearAll}>
            Clear
          </button>
        </div>
        <ul>
          {entries.map((e) => (
            <li key={e.id}>
              <button
                className={`history-item${e.id === selectedId ? " active" : ""}`}
                onClick={() => setParams({ id: e.id })}
              >
                <span className="history-q">{e.query}</span>
                <span className="history-meta">
                  <span className={`route-dot route-${e.route}`}>
                    {ROUTE_LABELS[e.route] || e.route}
                  </span>
                  {when(e.ts)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <div className="history-detail">
        {selected ? (
          <>
            <h1 className="history-title">{selected.query}</h1>
            <p className="memo-meta">{when(selected.ts)}</p>
            <Result result={selected} />
          </>
        ) : (
          <p className="status-msg">Select a past question to view it.</p>
        )}
      </div>
    </div>
  );
}
