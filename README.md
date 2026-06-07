# Reno Council Memo RAG

A retrieval + reasoning system over City of Reno council memos (Q1 2026 pilot,
77 memos). It is built to find **patterns across memos** — connections, tensions,
and timelines — not to summarize individual ones. Every answer is traceable to
the memos it cites.

See `ARCHITECTURE.md` for the design and `CLAUDE.md` for the build constraints.

## Layers

```
Knowledge   reno.db (SQLite + FTS5)        <- ingest.py
Retrieval   FTS5 keyword + graph walk +    <- query.py
            direct lookup (threads/flags/metrics)
Reasoning   Claude cross-document synthesis <- query.py
Interface   FastAPI JSON API + React SPA   <- api.py, web/
```

## Setup

Python (backend):

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

Build the database from the workbook (verifies row counts):

```bash
./.venv/bin/python ingest.py            # -> reno.db
```

Frontend deps:

```bash
cd web && npm install && cd ..
```

## Run

Two processes. **The API uses port 8077** (ports 5000 and 8000 are commonly
taken on macOS — AirPlay and other dev servers); the frontend uses **5180**.

```bash
# 1. API (set the key to enable cross-document synthesis; optional)
ANTHROPIC_API_KEY=sk-...  ./.venv/bin/uvicorn api:app --reload --port 8077

# 2. Frontend (separate terminal)
cd web && npm run dev
```

Open <http://localhost:5180>. The Vite dev server proxies `/api` to the backend.

Without `ANTHROPIC_API_KEY`, direct lookups (threads, flags, metrics) work fully
and keyword queries still retrieve and cite the relevant memos — only the written
synthesis paragraph is disabled.

## Command line

`query.py` is the engine and works standalone:

```bash
./.venv/bin/python query.py "how are DMV holds affecting parking revenue?"
./.venv/bin/python query.py --no-llm "what are the high priority flags?"
```

## How a query is routed

```
flags question      -> flags table (by priority)
metric question     -> metric series (when the query names one + asks quantitatively)
issue-thread named  -> thread + its memos
otherwise           -> FTS5 keyword search -> one-hop graph walk -> Claude synthesis
```

Direct-lookup routes never call the LLM. Reasoning is reserved for genuine
cross-document questions.

## What this is not

A summarizer of single memos, a keyword search box, or a source of claims about
the world beyond what the memos say. It distinguishes **what the memos say**
(faithful) from **what is true** (true) and labels uncertainty.
