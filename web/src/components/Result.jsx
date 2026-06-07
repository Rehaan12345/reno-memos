import ReactMarkdown from "react-markdown";
import MemoCard from "./MemoCard.jsx";
import ThreadCard from "./ThreadCard.jsx";
import FlagCard from "./FlagCard.jsx";
import MetricCard from "./MetricCard.jsx";
import Citations from "./Citations.jsx";

const ROUTE_LABELS = {
  reasoning: "Cross-document synthesis",
  threads: "Issue thread",
  flags: "Escalation flags",
  metrics: "Metric series",
};

// Renders a single search result. Shared by the live Ask page and the saved
// History view so a stored chat looks identical to a fresh one.
export default function Result({ result }) {
  const { route, answer, memos = [] } = result;
  return (
    <section className="result">
      <div className="result-head">
        <span className={`route-badge route-${route}`}>
          {ROUTE_LABELS[route] || route}
        </span>
        <Citations ids={result.memo_ids} />
      </div>

      {route === "reasoning" && <ReasoningAnswer answer={answer} memos={memos} />}

      {route === "threads" &&
        result.threads?.map((t) => <ThreadCard key={t.name} thread={t} />)}
      {route === "flags" &&
        result.flags?.map((f) => <FlagCard key={f.flag} flag={f} />)}
      {route === "metrics" &&
        result.metrics?.map((m) => <MetricCard key={m.series_name} metric={m} />)}

      {route !== "reasoning" && memos.length > 0 && (
        <details className="evidence">
          <summary>Supporting memos ({memos.length})</summary>
          <div className="memo-grid">
            {memos.map((m) => (
              <MemoCard key={m.global_id} memo={m} compact />
            ))}
          </div>
        </details>
      )}
    </section>
  );
}

function ReasoningAnswer({ answer, memos }) {
  // The backend prefixes this marker when no API key is configured.
  const degraded = answer?.startsWith("[Reasoning layer unavailable");
  return (
    <>
      {degraded ? (
        <div className="notice">
          <strong>Synthesis is offline.</strong> Set <code>ANTHROPIC_API_KEY</code>{" "}
          on the API server to get a written cross-document analysis. The relevant
          memos were still retrieved and are shown below.
        </div>
      ) : (
        <div className="answer markdown">
          <ReactMarkdown>{answer}</ReactMarkdown>
        </div>
      )}
      <h3 className="evidence-title">Evidence ({memos.length} memos)</h3>
      <div className="memo-grid">
        {memos.map((m) => (
          <MemoCard key={m.global_id} memo={m} />
        ))}
      </div>
    </>
  );
}
