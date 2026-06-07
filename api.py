"""
api.py — FastAPI JSON API over the retrieval + reasoning pipeline in query.py.

The React frontend (web/) consumes these endpoints. query.py remains the engine;
this layer only serializes its output. Direct-lookup routes (threads / flags /
metrics) work with no API key; the reasoning route calls Claude when
ANTHROPIC_API_KEY is set and otherwise returns the prepared, citation-ready
context so the system is still useful.

Run:
    ANTHROPIC_API_KEY=...  ./.venv/bin/uvicorn api:app --reload --port 5000
The Vite dev server proxies /api to this port (see web/vite.config.js).
"""

import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import query

app = FastAPI(title="Reno Memo RAG")

# The Vite dev server (5180) proxies /api here, so CORS isn't needed in the
# default setup; these origins cover the case of calling the API directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5180", "http://127.0.0.1:5180"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def jloads(s):
    try:
        return json.loads(s) if s else []
    except (ValueError, TypeError):
        return []


# JSON-array string columns -> real arrays for the frontend.
_ARRAY_FIELDS = {"memo_ids", "source_memos", "source_memo_ids", "periods", "data_values"}


def _expand(row):
    out = dict(row)
    for f in _ARRAY_FIELDS:
        if f in out and isinstance(out[f], str):
            out[f] = jloads(out[f])
    return out


@app.get("/api/stats")
def stats():
    conn = query.connect()
    try:
        tables = ["memos", "threads", "flags", "decisions", "metrics", "relationships"]
        counts = {
            t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables
        }
    finally:
        conn.close()
    return {"counts": counts, "llm_enabled": bool(os.environ.get("ANTHROPIC_API_KEY"))}


@app.get("/api/search")
def search(q: str = ""):
    q = q.strip()
    if not q:
        raise HTTPException(status_code=400, detail="missing query parameter 'q'")
    result = query.answer(q)

    conn = query.connect()
    try:
        memos_full = query.get_memos(conn, result.get("memo_ids", []))
    finally:
        conn.close()

    payload = {
        "query": q,
        "route": result["route"],
        "answer": result.get("answer"),
        "memo_ids": result.get("memo_ids", []),
        "memos": memos_full,
    }
    for key in ("flags", "metrics", "threads"):
        if key in result:
            payload[key] = [_expand(row) for row in result[key]]
    return payload


@app.get("/api/threads")
def threads():
    conn = query.connect()
    try:
        return [_expand(r) for r in query.lookup_threads(conn)]
    finally:
        conn.close()


@app.get("/api/flags")
def flags(priority: str | None = None):
    conn = query.connect()
    try:
        return [_expand(r) for r in query.lookup_flags(conn, priority)]
    finally:
        conn.close()


@app.get("/api/metrics")
def metrics():
    conn = query.connect()
    try:
        return [_expand(r) for r in query.lookup_metrics(conn)]
    finally:
        conn.close()


@app.get("/api/decisions")
def decisions():
    conn = query.connect()
    try:
        return query.lookup_decisions(conn)
    finally:
        conn.close()


@app.get("/api/memo/{global_id}")
def memo(global_id: str):
    conn = query.connect()
    try:
        rows = query.get_memos(conn, [global_id])
        if not rows:
            raise HTTPException(status_code=404, detail="memo not found")
        return {"memo": rows[0], "related": query.graph_walk(conn, [global_id])}
    finally:
        conn.close()
