import React, { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { GraphModal } from "@reno/graph";

const EMPTY = {
  more_accurate: "", accuracy_reason: "",
  wrong_output1: "", wrong_output2: "",
  invents_output1: "", invents_output2: "",
  extraction_output1: "", extraction_output2: "",
};

export default function App() {
  const [prompts, setPrompts] = useState([]);
  const [promptId, setPromptId] = useState(null);
  const [experiment, setExperiment] = useState("A");
  const [pair, setPair] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [savedAt, setSavedAt] = useState(null);
  const [unblind, setUnblind] = useState(null);

  useEffect(() => {
    fetch("/api/prompts").then((r) => r.json()).then((d) => {
      setPrompts(d);
      if (d.length) setPromptId(d[0].id);
    });
  }, []);

  useEffect(() => {
    if (!promptId) return;
    setUnblind(null);
    setSavedAt(null);
    fetch(`/api/pair?prompt_id=${promptId}&experiment=${experiment}`)
      .then((r) => r.json())
      .then((d) => {
        setPair(d);
        setForm(d.saved_response ? { ...EMPTY, ...d.saved_response } : EMPTY);
      });
  }, [promptId, experiment]);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const save = () => {
    fetch("/api/response", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt_id: promptId, experiment, ...form }),
    })
      .then((r) => r.json())
      .then(() => setSavedAt(new Date().toLocaleTimeString()));
  };

  const doUnblind = () => {
    if (!window.confirm(
      "Reveal which system produced each output? Do this only after you have " +
      "recorded your judgment — it cannot be un-seen.")) return;
    fetch(`/api/unblind?prompt_id=${promptId}&experiment=${experiment}`, { method: "POST" })
      .then((r) => r.json())
      .then((d) => setUnblind(d.mapping));
  };

  return (
    <div className="app">
      <aside className="sidebar">
        <h1>Blinded Review</h1>
        <p className="hint">Pick a prompt, judge the two outputs, save. Unblind is separate.</p>
        <ol className="prompt-list">
          {prompts.map((p) => (
            <li key={p.id}
                className={p.id === promptId ? "active" : ""}
                onClick={() => setPromptId(p.id)}>
              <span className="pid">{p.id}</span>
              <span className="ptext">{p.prompt}</span>
            </li>
          ))}
        </ol>
      </aside>

      <main className="main">
        {pair && (
          <>
            <div className="topbar">
              <div className="exp-toggle">
                {["A", "B"].map((x) => (
                  <button key={x}
                          className={x === experiment ? "on" : ""}
                          onClick={() => setExperiment(x)}>
                    Experiment {x}
                  </button>
                ))}
              </div>
              <div className="prompt-banner">{pair.prompt}</div>
            </div>

            <div className="outputs">
              {pair.outputs.map((o) => (
                <section className="output-card" key={o.label}>
                  <header className="output-head">
                    <h2>{o.label}</h2>
                    {unblind && <span className="revealed">{unblind[o.label]}</span>}
                  </header>

                  <div className="answer">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{o.answer}</ReactMarkdown>
                  </div>

                  <div className="sources">
                    <h3>Cited sources</h3>
                    {o.cited_sources.length === 0
                      ? <p className="none">(none cited)</p>
                      : <ul>{o.cited_sources.map((s, i) => (
                          <li key={i}>
                            {s.source_url
                              ? <a href={s.source_url} target="_blank" rel="noreferrer">{s.memo_id}</a>
                              : <span>{s.memo_id}</span>}
                            {s.title ? ` — ${s.title}` : ""}
                          </li>))}</ul>}
                  </div>

                  {o.extracted_data && <ExtractedData data={o.extracted_data} />}
                </section>
              ))}
            </div>

            <ExpertForm experiment={experiment} form={form} set={set}
                        setForm={setForm} />

            <div className="actions">
              <button className="save" onClick={save}>Save judgment</button>
              {savedAt && <span className="saved-msg">Saved at {savedAt}</span>}
              <button className="unblind" onClick={doUnblind}>Unblind ▸</button>
              {unblind && (
                <span className="unblind-msg">
                  Output 1 = {unblind["Output 1"]} · Output 2 = {unblind["Output 2"]}
                </span>
              )}
            </div>
          </>
        )}
      </main>
    </div>
  );
}

function ExtractedData({ data }) {
  const [open, setOpen] = useState(false);
  const [graphOpen, setGraphOpen] = useState(false);
  const ents = data.entities || [];
  const rels = data.relationships || [];
  const fields = data.fields || {};
  return (
    <div className="extracted">
      <div className="ex-head">
        <button className="ex-toggle" onClick={() => setOpen(!open)}>
          {open ? "▾" : "▸"} Extracted data behind this answer
          <span className="ex-counts"> · {ents.length} entities · {rels.length} relationships · {Object.keys(fields).length} memos</span>
        </button>
        <button className="ex-graph-btn" onClick={() => setGraphOpen(true)}>◓ View graph</button>
      </div>
      {graphOpen && <GraphModal extracted={data} onClose={() => setGraphOpen(false)} />}
      {open && (
        <div className="ex-body">
          <div className="ex-col">
            <h4>Entities</h4>
            <ul>{ents.map((e, i) => (
              <li key={i}><b>{e.name}</b> <i>{e.type}</i> — {(e.memo_ids || []).join(", ")}</li>
            ))}</ul>
          </div>
          <div className="ex-col">
            <h4>Relationships</h4>
            <ul>{rels.map((r, i) => (
              <li key={i}>{r.source_id} <b>{r.rel_type}</b> {r.target_id}
                {r.evidence ? <span className="ev"> — {r.evidence}</span> : null}</li>
            ))}</ul>
          </div>
          <div className="ex-col">
            <h4>Fields per memo</h4>
            {Object.entries(fields).map(([gid, f]) => (
              <div className="fieldset" key={gid}>
                <b>{gid}</b>
                <ul>{Object.entries(f).map(([k, v]) => v
                  ? <li key={k}><i>{k}:</i> {String(v).slice(0, 180)}</li> : null)}</ul>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ExpertForm({ experiment, form, set, setForm }) {
  return (
    <div className="form">
      <div className="q">
        <label>1 · Which output is more accurate to what actually happened in Reno?</label>
        <div className="radios">
          {["Output 1", "Output 2", "Tie"].map((opt) => (
            <label key={opt} className="radio">
              <input type="radio" name="acc" checked={form.more_accurate === opt}
                     onChange={() => setForm({ ...form, more_accurate: opt })} />
              {opt}
            </label>
          ))}
        </div>
        <input className="line" placeholder="One-line reason"
               value={form.accuracy_reason} onChange={set("accuracy_reason")} />
      </div>

      <div className="q two">
        <label>2 · Where is each output wrong, incomplete, or misleading?</label>
        <textarea placeholder="Output 1…" value={form.wrong_output1} onChange={set("wrong_output1")} />
        <textarea placeholder="Output 2…" value={form.wrong_output2} onChange={set("wrong_output2")} />
      </div>

      <div className="q two">
        <label>3 · Does either output invent, conflate, or misattribute anything?</label>
        <textarea placeholder="Output 1…" value={form.invents_output1} onChange={set("invents_output1")} />
        <textarea placeholder="Output 2…" value={form.invents_output2} onChange={set("invents_output2")} />
      </div>

      {experiment === "B" && (
        <div className="q two">
          <label>4 · (Experiment B) Is the extracted data behind each answer sound?
            Duplicate entities? Wrong/missing links? Fabrications?</label>
          <textarea placeholder="Output 1…" value={form.extraction_output1} onChange={set("extraction_output1")} />
          <textarea placeholder="Output 2…" value={form.extraction_output2} onChange={set("extraction_output2")} />
        </div>
      )}
    </div>
  );
}
