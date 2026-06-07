import Citations from "./Citations.jsx";

// Returns a priority tier ("high" | "medium" | "low") from the raw priority
// string, which includes an emoji (e.g. "🔴 High").
function tier(priority = "") {
  const p = priority.toLowerCase();
  if (p.includes("high")) return "high";
  if (p.includes("medium")) return "medium";
  return "low";
}

// An escalation flag: a signal that warrants attention, with a next step.
export default function FlagCard({ flag }) {
  const t = tier(flag.priority);
  const ids = flag.source_memos && flag.source_memos.length ? flag.source_memos : null;
  return (
    <article className={`panel flag-card flag-${t}`}>
      <header className="panel-head">
        <h3>{flag.flag}</h3>
        <span className={`priority priority-${t}`}>{flag.priority}</span>
      </header>
      <p className="signal">{flag.signal}</p>
      <dl className="kv">
        <div>
          <dt>Status</dt>
          <dd>{flag.status}</dd>
        </div>
        <div>
          <dt>Next step</dt>
          <dd>{flag.next_step}</dd>
        </div>
      </dl>
      {ids ? (
        <Citations ids={ids} />
      ) : (
        <div className="citations">
          <span className="citations-label">Sources</span>
          <span className="cite-text">{flag.source_raw}</span>
        </div>
      )}
    </article>
  );
}
