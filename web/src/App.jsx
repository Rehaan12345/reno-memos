import { Routes, Route, NavLink, Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { api } from "./api.js";
import Ask from "./pages/Ask.jsx";
import Memo from "./pages/Memo.jsx";
import History from "./pages/History.jsx";
import { Threads, Flags, Metrics, Decisions } from "./pages/Browse.jsx";

export default function App() {
  const [stats, setStats] = useState(null);
  useEffect(() => {
    api.stats().then(setStats).catch(() => {});
  }, []);

  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand">
          <span className="brand-mark">Reno</span> Memo Pattern Finder
        </Link>
        <nav className="mainnav">
          <NavLink to="/" end>
            Ask
          </NavLink>
          <NavLink to="/threads">Threads</NavLink>
          <NavLink to="/flags">Flags</NavLink>
          <NavLink to="/metrics">Metrics</NavLink>
          <NavLink to="/decisions">Decisions</NavLink>
          <NavLink to="/history">History</NavLink>
        </nav>
      </header>

      <main className="content">
        <Routes>
          <Route path="/" element={<Ask />} />
          <Route path="/threads" element={<Threads />} />
          <Route path="/flags" element={<Flags />} />
          <Route path="/metrics" element={<Metrics />} />
          <Route path="/decisions" element={<Decisions />} />
          <Route path="/history" element={<History />} />
          <Route path="/memo/:id" element={<Memo />} />
          <Route path="*" element={<p className="status-msg">Not found.</p>} />
        </Routes>
      </main>

      <footer className="footer">
        <p>
          {stats
            ? `${stats.counts.memos} memos · ${stats.counts.threads} threads · ${stats.counts.flags} flags · ${stats.counts.metrics} metrics · ${stats.counts.relationships} relationships`
            : "Loading…"}
          {stats && !stats.llm_enabled && " · synthesis offline (no API key)"}
        </p>
        <p className="disclaimer">
          Pilot over public City of Reno council memos (Q1 2026). Generated
          analysis is not authoritative — always check the cited memo. This tool
          reports what the memos say, which is not the same as what is true.
        </p>
      </footer>
    </div>
  );
}
