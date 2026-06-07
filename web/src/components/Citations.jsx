import { Link } from "react-router-dom";

// Inline list of cited global_ids, each linking to its memo.
export default function Citations({ ids }) {
  if (!ids || ids.length === 0) return null;
  return (
    <div className="citations">
      <span className="citations-label">Sources</span>
      {ids.map((id) => (
        <Link key={id} to={`/memo/${id}`} className="cite-chip">
          {id}
        </Link>
      ))}
    </div>
  );
}
