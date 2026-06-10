import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import { api } from "../api.js";
import { ResponseGraph } from "@reno/graph";
import Citations from "../components/Citations.jsx";
import MemoCard from "../components/MemoCard.jsx";

const EXAMPLES = [
  "How are DMV holds affecting parking revenue?",
  "What's happening with homelessness and outreach?",
  "What are the tensions across departments this quarter?",
];

// B-research view: answers a question over the self-built knowledge base and
// shows the evidence graph (memos, entities, relationships) behind the answer.
export default function Research() {
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
      .research(q)
      .then((r) => active && setResult(r))
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
        <h1>See the reasoning behind the answer</h1>
        <p className="lede">
          Ask a question and see the memos, entities, and relationships the system
          used to answer it — the evidence trail, drawn as a graph.
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

      {loading && <p className="status-msg">Researching…</p>}
      {error && <p className="status-msg error">Error: {error}</p>}
      {result && !loading && <ResearchResult result={result} />}
    </div>
  );
}

function ResearchResult({ result }) {
  const { answer, extracted_data, retrieved_chunk_ids = [], cited_sources = [] } = result;
  const degraded = answer?.startsWith("[Reasoning layer unavailable");
  const fields = extracted_data?.fields || {};
  const memos = cited_sources.map((c) => ({ global_id: c.memo_id, ...fields[c.memo_id] }));

  return (
    <section className="result">
      <div className="result-head">
        <span className="route-badge route-reasoning">Cross-document synthesis</span>
        <Citations ids={retrieved_chunk_ids} />
      </div>

      {degraded ? (
        <div className="notice">
          <strong>Synthesis is offline.</strong> Set <code>ANTHROPIC_API_KEY</code> on
          the API server for a written analysis. The evidence graph below is built
          from retrieval and needs no key.
        </div>
      ) : (
        <div className="answer markdown">
          <ReactMarkdown>{answer}</ReactMarkdown>
        </div>
      )}

      <h3 className="evidence-title">Evidence graph</h3>
      <ResponseGraph
        extracted={extracted_data || {}}
        memoIds={retrieved_chunk_ids}
        nodeHref={(n) => (n.kind === "memo" ? `/memo/${n.id}` : null)}
      />

      <h3 className="evidence-title">Memos ({memos.length})</h3>
      <div className="memo-grid">
        {memos.map((m) => (
          <MemoCard key={m.global_id} memo={m} />
        ))}
      </div>
    </section>
  );
}
