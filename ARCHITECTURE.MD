# Reno Memo RAG — Architecture Document

## Purpose of this document

This is the build spec. It describes what to build, in what order, and why
each decision was made. The CLAUDE.md encodes the constraints the agent must
follow. This document explains the system's intended structure so the agent
understands the intent behind those constraints.

---

## What we're starting from

The CityThread Q1 2026 spreadsheet already contains 77 structured memos
across 8 sheets. The extraction work is done. We are not building a PDF
parsing pipeline right now — we are building a RAG system on top of
already-structured data.

Sheet inventory:
- `01 · Master Log` — 77 memos, 18 columns each
- `02 · Metrics` — 18 quantitative time-series extracted from memos
- `03 · Issue Threads` — 12 pre-built cross-memo storylines
- `04 · Decisions` — 14 extracted decisions with maker and impact
- `05 · Flags` — 10 escalation signals with priority and next step
- `06 · Agent Context` — a single-cell prompt stub (ignore this)
- `07 · Category Key` — 18 normalized category labels with counts

This is the richest part of the project. The threads, flags, and metrics
sheets represent human-curated cross-document analysis that already answers
the question "what connects these memos?" The RAG system's job is to make
that analysis queryable and extensible.

---

## System overview

Three distinct layers, built and tested in order. Do not collapse layers
or combine responsibilities across them.

```
┌─────────────────────────────────┐
│  KNOWLEDGE LAYER                │
│  SQLite database                │
│  memos, relationships,          │
│  threads, flags, decisions,     │
│  metrics, FTS5 index            │
└──────────────┬──────────────────┘
               │
┌──────────────▼──────────────────┐
│  RETRIEVAL LAYER                │
│  FTS5 keyword search            │
│  Relationship graph walk        │
│  Thread / flag direct lookup    │
└──────────────┬──────────────────┘
               │
┌──────────────▼──────────────────┐
│  REASONING LAYER                │
│  Claude with structured prompt  │
│  Cross-document synthesis       │
│  Citation-grounded output       │
└─────────────────────────────────┘
```

---

## Layer 1 — Knowledge Layer

### What it is

A SQLite database containing all spreadsheet data in queryable form, plus a
full-text search index over memo content.

### Why SQLite and not a vector database

The Q1 2026 dataset has 77 memos. Vector databases solve the problem of
finding semantically similar documents across tens of thousands of items.
At 77, keyword search with FTS5 is faster, more transparent, and easier to
debug. Embeddings are a future concern when the dataset grows or when
keyword search demonstrably misses relevant memos.

### Tables to build

**memos** — one row per memo, all structured fields from the master log.
The `search_text` column concatenates all text fields for FTS indexing.
`global_id` is the primary key across the entire system.

**relationships** — typed edges derived from the `Related Memos` column.
One row per directed edge: `(source_id, target_id, rel_type)`.
Default rel_type is `references`. Approved types are in CLAUDE.md.

**threads** — one row per issue thread from sheet 03. Store memo_ids as a
JSON array. Monthly summaries stored as separate columns (jan, feb, mar,
apr) so they can be queried individually.

**flags** — one row per escalation flag from sheet 05. Priority, signal,
source memo_ids (JSON array), status, next_step.

**decisions** — one row per decision from sheet 04. Include global_id
(maps to memos.global_id), date, department, decision text, made_by,
category, impact.

**metrics** — one row per time-series from sheet 02. Store periods and
data_values as parallel JSON arrays. Include series_name, unit, description,
source_memo_ids (JSON array).

**memos_fts** — FTS5 virtual table over memos.search_text. Used for all
keyword retrieval.

### Ingestion rules

- Use `INSERT OR REPLACE` so re-ingesting updated spreadsheet data is safe
- Parse the `Related Memos` column carefully — it contains formats like
  `"002, 004"`, `"FEB-008,MAR-003"`, and `"001 (Dec), 003 (parking)"`.
  Strip parenthetical notes. Normalize to full global_id format where possible.
- The metrics sheet has an irregular layout — series names, source rows,
  period rows, and value rows are not in a standard tabular structure.
  Parse by scanning for sentinel patterns, not by column position.
- Build the FTS5 index after all memos are inserted.

---

## Layer 2 — Retrieval Layer

### Three retrieval modes

**Keyword retrieval** — FTS5 search over memos.search_text. The input
natural language query must be pre-processed to extract content words
before passing to FTS5. Strip stop words. Use OR matching so partial
keyword matches return results rather than nothing.

**Direct lookup** — threads, flags, and decisions tables support direct
queries by name, priority, or category without going through FTS5. These
pre-built structures encode existing cross-document analysis and should
be the first response for obvious questions like "what are the active
issues?" or "what flags are high priority?"

**Relationship graph walk** — given a set of retrieved memos, walk the
relationships table one hop to find connected memos not already in the
result set. This is how the system discovers that a parking revenue memo
is connected to a DMV hold memo even if the query didn't mention DMV.
Limit to one hop for Q1 2026. Two-hop traversal can be added when the
graph is denser.

### Retrieval routing logic

```
Query arrives
    ↓
Is it a direct thread question? ("what's happening with X")
    → Look up threads by name, return thread + constituent memos
    
Is it a flags question? ("what are the high priority issues")
    → Return flags table filtered by priority
    
Is it a metric question? ("show me parking revenue over time")
    → Look up metrics by series name, return time-series data
    
Otherwise:
    → Keyword retrieval via FTS5
    → Expand retrieved set via one-hop graph walk
    → Pass to reasoning layer
```

### What retrieval must always return

Every retrieval path must return `global_id` alongside content. No
function may return memo content without its source ID. This is enforced
at the function signature level, not as an afterthought.

---

## Layer 3 — Reasoning Layer

### What it does

Takes a set of retrieved memos and a query, builds a structured context
block, and calls Claude to reason across the memos — not to summarize them.

### System prompt requirements

The system prompt must instruct Claude to:
- Identify patterns, tensions, timelines, and gaps — not describe individual memos
- Cite specific global_ids as evidence for every claim
- Distinguish faithful claims (what the memos say) from true claims (what is
  true in the world) — these are different things and must not be conflated
- Return the source memo directly if a question is answerable from one memo
- Use plain language — no jargon, no raw field names in output
- Label uncertainty explicitly ("the memos suggest" not "it is the case")

### Context block format

Each memo in the context block should include:
- global_id
- title
- date_published
- department
- tldr
- key_stats (if present)
- key_decisions (if present)
- action_items (if present)

Separate memos with a clear delimiter. Keep the total context under a
size limit so it fits reliably in the model's context window. Truncate
from the bottom (least relevant memos) if needed.

### What the reasoning layer must not do

- Invent content not present in the retrieved memos
- Merge questions that require different retrieval paths into one LLM call
- Call Claude when direct lookup would suffice (threads, flags, metrics)

---

## File structure

```
reno_rag/
├── CLAUDE.md           ← agent instructions (constraints, conventions)
├── ARCHITECTURE.md     ← this document (intent and build spec)
├── ingest.py           ← load spreadsheet → SQLite
├── query.py            ← retrieval + reasoning entry point
├── reno.db             ← SQLite database (gitignored)
└── docs/
    └── research-rationale.md  ← maps decisions to source papers
```

One ingest script. One query script. No premature abstraction.
Add a web layer only after the CLI works correctly end to end.

---

## Build order

Build and verify each step before starting the next. Do not skip ahead.

**Step 1 — Ingest**
Load all 6 sheets into SQLite. Verify row counts match the spreadsheet.
Build FTS5 index. Confirm keyword search returns expected memos before
writing any retrieval logic.

**Step 2 — Direct lookup**
Implement threads, flags, and decisions retrieval. These require no LLM
and produce verifiable output. Test each against the spreadsheet by hand.

**Step 3 — Keyword retrieval**
Implement FTS5 retrieval with stop-word filtering. Confirm it returns
relevant memos for representative queries before adding graph walk.

**Step 4 — Graph walk**
Add one-hop relationship expansion. Verify that it surfaces genuinely
related memos rather than noise.

**Step 5 — Reasoning layer**
Implement Claude call with structured system prompt. Test on queries that
require cross-document synthesis. Evaluate output against the rubric in
CLAUDE.md.

**Step 6 — Evaluation**
Run retrieval evaluation (precision@k) and generate a small human-labeled
reference set for insight evaluation. Do not claim the system works without
evidence.

---

## What this system is not

- A PDF ingestion pipeline (memos are already extracted)
- A general-purpose civic data tool (scoped to Reno council memos)
- A replacement for human judgment on policy questions
- Production-ready (this is a pilot on 77 memos)

The next meaningful expansion is adding Q2 2026 memos, not adding
capabilities. Get the Q1 system working correctly first.

---

## Decisions deferred and why

**Vector embeddings** — deferred. FTS5 is sufficient for 77 memos and
easier to debug. Revisit when the dataset exceeds a few hundred memos or
when FTS5 demonstrably misses relevant results.

**Web UI** — deferred. The CLI must work correctly first. A broken system
with a polished UI is still a broken system.

**Multi-hop graph traversal** — deferred. The relationship graph currently
has 94 edges across 77 memos. One-hop traversal is sufficient. Two-hop
adds complexity and noise before the graph is dense enough to warrant it.

**Automated PDF ingestion** — deferred. The extraction quality in the
CityThread spreadsheet is high and consistent. Automating extraction means
inheriting all the PDF quality and parsing complexity before the downstream
system is validated.