import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api } from "../api.js";
import MemoCard from "../components/MemoCard.jsx";

const FIELDS = [
  ["tldr", "Summary"],
  ["key_stats", "Key stats"],
  ["key_decisions", "Key decisions"],
  ["action_items", "Action items & deadlines"],
  ["keywords", "Keywords"],
];

export default function Memo() {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;
    setData(null);
    setError(null);
    api
      .memo(id)
      .then((d) => active && setData(d))
      .catch((e) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [id]);

  if (error) return <p className="status-msg error">{error}</p>;
  if (!data) return <p className="status-msg">Loading…</p>;

  const { memo, related } = data;
  return (
    <div className="memo-detail">
      <Link to="/" className="back">
        ← Ask another question
      </Link>
      <header className="memo-detail-head">
        <span className="gid big">{memo.global_id}</span>
        <h1>{memo.title}</h1>
        <p className="memo-meta">
          {memo.date_published} · {memo.department}
          {memo.authors ? ` · ${memo.authors}` : ""}
        </p>
        <div className="tags">
          {memo.category && <span className="tag">{memo.category}</span>}
          {memo.subcategory && <span className="tag">{memo.subcategory}</span>}
        </div>
      </header>

      <dl className="memo-fields">
        {FIELDS.map(([key, label]) =>
          memo[key] ? (
            <div key={key}>
              <dt>{label}</dt>
              <dd>{memo[key]}</dd>
            </div>
          ) : null
        )}
      </dl>

      {memo.source_url && (
        <p>
          <a href={memo.source_url} target="_blank" rel="noreferrer" className="source-link">
            View the original memo (PDF) ↗
          </a>
        </p>
      )}

      {related.length > 0 && (
        <section className="related">
          <h2>Related memos</h2>
          <p className="lede">
            Connected through the relationship graph — one hop from this memo.
          </p>
          <div className="memo-grid">
            {related.map((m) => (
              <MemoCard key={m.global_id} memo={m} compact />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
