import { useEffect, useState } from "react";
import { api } from "../api.js";
import ThreadCard from "../components/ThreadCard.jsx";
import FlagCard from "../components/FlagCard.jsx";
import MetricCard from "../components/MetricCard.jsx";

// Generic data-loading wrapper for the browse pages.
function useResource(loader) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    let active = true;
    loader()
      .then((d) => active && setData(d))
      .catch((e) => active && setError(e.message));
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return { data, error };
}

function Page({ title, intro, children }) {
  return (
    <div className="browse">
      <header className="browse-head">
        <h1>{title}</h1>
        <p className="lede">{intro}</p>
      </header>
      {children}
    </div>
  );
}

export function Threads() {
  const { data, error } = useResource(api.threads);
  return (
    <Page
      title="Issue threads"
      intro="Human-curated storylines that connect memos across the quarter. Each thread tracks one issue month by month."
    >
      {error && <p className="status-msg error">{error}</p>}
      {data?.map((t) => (
        <ThreadCard key={t.name} thread={t} />
      ))}
    </Page>
  );
}

export function Flags() {
  const { data, error } = useResource(api.flags);
  return (
    <Page
      title="Escalation flags"
      intro="Signals pulled from across the memos that may warrant attention, ordered by priority."
    >
      {error && <p className="status-msg error">{error}</p>}
      {data?.map((f) => (
        <FlagCard key={f.flag} flag={f} />
      ))}
    </Page>
  );
}

export function Metrics() {
  const { data, error } = useResource(api.metrics);
  return (
    <Page
      title="Metrics"
      intro="Quantitative time-series extracted from the memos. Every series is traceable to its source memos."
    >
      {error && <p className="status-msg error">{error}</p>}
      {data?.map((m) => (
        <MetricCard key={m.series_name} metric={m} />
      ))}
    </Page>
  );
}

export function Decisions() {
  const { data, error } = useResource(api.decisions);
  return (
    <Page
      title="Decisions"
      intro="Decisions made or recommended in the memos, with who made them and their stated impact."
    >
      {error && <p className="status-msg error">{error}</p>}
      <div className="decisions-list">
        {data?.map((d, i) => (
          <DecisionRow key={i} d={d} />
        ))}
      </div>
    </Page>
  );
}

function DecisionRow({ d }) {
  return (
    <article className="panel decision-row">
      <header className="panel-head">
        <a className="gid" href={`/memo/${d.global_id}`}>
          {d.global_id}
        </a>
        <span className="memo-meta">
          {d.date} · {d.department}
        </span>
      </header>
      <p className="decision-text">{d.decision}</p>
      <dl className="kv">
        <div>
          <dt>Made by</dt>
          <dd>{d.made_by}</dd>
        </div>
        <div>
          <dt>Category</dt>
          <dd>{d.category}</dd>
        </div>
        <div>
          <dt>Impact</dt>
          <dd>{d.impact}</dd>
        </div>
      </dl>
    </article>
  );
}
