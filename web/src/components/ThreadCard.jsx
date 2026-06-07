import Citations from "./Citations.jsx";

const MONTHS = [
  ["jan", "Jan"],
  ["feb", "Feb"],
  ["mar", "Mar"],
  ["apr", "Apr"],
];

// An issue thread: a human-curated cross-memo storyline with monthly progress.
export default function ThreadCard({ thread }) {
  return (
    <article className="panel thread-card">
      <header className="panel-head">
        <h3>{thread.name}</h3>
        <span className={`status status-${(thread.status || "").toLowerCase()}`}>
          {thread.status}
        </span>
      </header>
      {thread.key_signal && <p className="signal">{thread.key_signal}</p>}
      <div className="timeline">
        {MONTHS.map(([key, label]) =>
          thread[key] ? (
            <div className="timeline-step" key={key}>
              <span className="timeline-month">{label}</span>
              <span className="timeline-text">{thread[key]}</span>
            </div>
          ) : null
        )}
      </div>
      <Citations ids={thread.memo_ids} />
    </article>
  );
}
