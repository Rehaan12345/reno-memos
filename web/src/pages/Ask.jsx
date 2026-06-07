import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import Result from "../components/Result.jsx";
import { saveHistory } from "../history.js";

const EXAMPLES = [
  "How are DMV holds affecting parking revenue?",
  "What's happening with homelessness and outreach?",
  "What are the high priority flags?",
  "Show me Clean & Safe arrests over time",
  "What decisions has the Council made about parking?",
];

export default function Ask() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") || "";
  const [input, setInput] = useState(q);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    setInput(q);
    if (!q) {
      setResult(null);
      return;
    }
    let active = true;
    setLoading(true);
    setError(null);
    api
      .search(q)
      .then((r) => {
        if (!active) return;
        setResult(r);
        saveHistory(r);
      })
      .catch((e) => active && setError(e.message))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [q]);

  function submit(e) {
    e.preventDefault();
    const trimmed = input.trim();
    if (trimmed) setParams({ q: trimmed });
  }

  return (
    <div className="ask">
      <section className="hero">
        <h1>Find patterns across Reno council memos</h1>
        <p className="lede">
          Ask about connections, tensions, and timelines spanning many memos —
          not just what one memo says. Every answer is traced back to its sources.
        </p>
        <form className="searchbar" onSubmit={submit}>
          <input
            type="text"
            value={input}
            placeholder="Ask a question…"
            onChange={(e) => setInput(e.target.value)}
            autoFocus
          />
          <button type="submit">Ask</button>
        </form>
        {!q && (
          <div className="examples">
            {EXAMPLES.map((ex) => (
              <button key={ex} className="chip" onClick={() => setParams({ q: ex })}>
                {ex}
              </button>
            ))}
          </div>
        )}
      </section>

      {loading && <p className="status-msg">Searching…</p>}
      {error && <p className="status-msg error">Error: {error}</p>}
      {result && !loading && <Result result={result} />}
    </div>
  );
}
