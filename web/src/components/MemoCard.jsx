import { Link } from "react-router-dom";

// A single memo, shown as evidence. The global_id is always visible and links
// to the full memo — every claim in this system is traceable to a source.
export default function MemoCard({ memo, compact = false }) {
  if (!memo) return null;
  return (
    <article className={`memo-card${compact ? " compact" : ""}`}>
      <header>
        <Link to={`/memo/${memo.global_id}`} className="gid">
          {memo.global_id}
        </Link>
        <span className="memo-meta">
          {memo.date_published ? `${memo.date_published} · ` : ""}
          {memo.department}
        </span>
      </header>
      <Link to={`/memo/${memo.global_id}`} className="memo-title">
        {memo.title}
      </Link>
      {!compact && memo.tldr && <p className="memo-tldr">{memo.tldr}</p>}
      {memo.category && <span className="tag">{memo.category}</span>}
    </article>
  );
}
