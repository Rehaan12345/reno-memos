# Reno Council Memo RAG

A retrieval + reasoning system over City of Reno council memos (77 memos,
January–April 2026). It is built to find **patterns across memos** — connections,
tensions, and timelines — not to summarize individual ones. Every answer is
traceable to the memos it cites.

The repo contains two things:

1. **The base system** — a research-grounded RAG over the curated CityThread
   spreadsheet, with a FastAPI + React UI. (This is the system labelled
   *A-research* in the evaluation.)
2. **An evaluation harness** (`eval/`) — a blinded, expert-judged comparison of
   **four** systems across **two experiments**, testing whether grounding a RAG
   system in published research actually changes output quality.

See `ARCHITECTURE.md` for the base design, `CLAUDE.md` for the build constraints,
and the doc map at the bottom for everything else.

---

## Part 1 — The base system

### Layers
```
Knowledge   reno.db (SQLite + FTS5)         <- ingest.py
Retrieval   FTS5 keyword + graph walk +     <- query.py
            direct lookup (threads/flags/metrics)
Reasoning   Claude cross-document synthesis <- query.py
Interface   FastAPI JSON API + React SPA    <- api.py, web/
```

### Setup
```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt   # includes the eval deps too
./.venv/bin/python ingest.py                  # build reno.db from the workbook
cd web && npm install && cd ..                # frontend deps
```

### Run
Two processes. **The API uses port 8077** (5000/8000 are often taken on macOS);
the frontend uses **5180**.
```bash
ANTHROPIC_API_KEY=sk-...  ./.venv/bin/uvicorn api:app --reload --port 8077
cd web && npm run dev                          # separate terminal
```
Open <http://localhost:5180>. Vite proxies `/api` to the backend. Without a key,
direct lookups still work and queries still retrieve + cite — only the written
synthesis is disabled.

### Command line
```bash
./.venv/bin/python query.py "how are DMV holds affecting parking revenue?"
./.venv/bin/python query.py --no-llm "what are the high priority flags?"
```

### How a query is routed
```
flags question      -> flags table (by priority)
metric question     -> metric series (when the query names one + asks quantitatively)
issue-thread named  -> thread + its memos
otherwise           -> FTS5 keyword search -> one-hop graph walk -> Claude synthesis
```
Direct-lookup routes never call the LLM. Reasoning is reserved for genuine
cross-document questions.

### Graph views

Two pages visualize the relationship graph (memos joined by typed edges).
Both render with `@reno/graph`, a shared React package (`packages/graph/`)
consumed by the web app and the eval review UI from source — edit it once and
both apps pick the change up live.

- **Research** (`/research`) — answers a question and draws the *per-answer*
  evidence graph: just the memos that fed the answer, plus a toggle to add the
  entities (departments / projects / people) they mention.
- **Graph** (`/graph`) — the *whole* knowledge base: all 77 memos and 165 typed
  edges, with a per-relation-type filter.

**How to read it** (also shown in-app under "How to read this graph"):

- **Dots are memos**, labeled by ID and colored by department. In the
  "Memos + entities" view, unlabeled dots are entities — blue = department,
  green = project, orange = person.
- **Lines are relationships**, colored by type. An **arrowhead** means
  direction (source → target).
  - **Blue, no arrow — `same_project`**: the memos share a named project. ~75%
    of edges are these, so the default view is mostly topic clustering.
  - **Orange, arrow — `precedes`**: the source memo comes before the target in
    time or logic. Follow arrow chains to read a storyline.
  - **Purple, arrow — `references`**: one memo explicitly cites another.
- **Hover** a line for the evidence behind it; hover a dot for its title.
- On the global graph, **click `same_project` off in the legend** to strip the
  clustering edges and see the `precedes` chains — the real cross-document
  structure.

---

## Part 2 — The evaluation harness (`eval/`)

A side-by-side, **blinded, expert-judged** comparison. There is **no automated
scoring and no LLM-as-judge** anywhere — the expert is the only evaluator.

### The four systems

| System | Experiment | Data source | Grounding |
|--------|-----------|-------------|-----------|
| **A-research** | A | spreadsheet (`reno.db`) | full (CLAUDE.md + ARCHITECTURE.md) |
| **A-vanilla**  | A | spreadsheet rows, flattened | none (control) |
| **B-research** | B | raw council PDFs | full extraction pipeline |
| **B-vanilla**  | B | raw PDF text | none (control) |

- **Experiment A** isolates grounding's effect on *retrieval + reasoning* (both
  systems start from clean, curated data).
- **Experiment B** tests grounding on *the whole pipeline including extraction*
  (both start from raw PDFs). B-research builds its own structured knowledge base
  from the PDFs; B-vanilla just chunks their text.

Within each pair, **only research grounding varies** — model, generation params
(`claude-sonnet-4-6`, max_tokens 2048, temperature 0), the prompt text, and the
document set are held constant.

### The contract (single source of truth — nothing is hardcoded around it)
- `eval/prompts.json` — the locked 15-prompt set. Each prompt's `reference_key`
  is internal-only; it is never sent to a system or shown to the expert.
- `eval/systems.config.json` — per-system config (model, chunk size, top-k,
  embedding model, generic prompt, Experiment B ingestion filters).
- `eval/run-record.schema.json` — the shape of each append-only run record.

### Pipeline
```bash
# 1. Resolve the Experiment B document set (live PDFs, filtered + fetched + logged)
./.venv/bin/python eval/experiment_b_ingest.py        # --dry-run to classify without fetching

# 2. Build indexes / knowledge bases
./.venv/bin/python eval/vanilla_rag.py --build A-vanilla
./.venv/bin/python eval/vanilla_rag.py --build B-vanilla
./.venv/bin/python eval/experiment_b_research.py --build   # cached; --rebuild to force
# (A-research uses the existing reno.db via query.py — nothing to build)

# 3. Run every prompt through every system (append-only -> eval/runs/)
./.venv/bin/python eval/runner.py                     # or --prompt P01 / --system A-vanilla
```

### Blinded review UI
```bash
cd eval && ../.venv/bin/uvicorn review_api:app --reload --port 8088   # backend
cd eval/review && npm install && npm run dev                          # http://localhost:5190
```
- Pick a prompt, toggle Experiment A / B, judge the two blinded outputs, **Save**.
- Left/right order is randomized once and persisted (`eval/review/blind_map.json`).
- Experiment B also shows the structured data each system built (entities /
  relationships / fields), with a **View graph** button that pops out the same
  evidence graph as the Research page.
- **Unblind** is a separate, confirm-gated action; system identity is never shown
  by default.
- Answers save to `eval/review/responses/{prompt}__{experiment}.json` with the
  blind mapping attached.

### Notes
- All four systems generate with the shared params above; the vanilla pair uses a
  local `sentence-transformers/all-MiniLM-L6-v2` embedder (no API key needed).
- The two B systems consume the byte-identical document set; the runner asserts a
  single shared `document_set_hash` before any B run.

---

## What this is not

A summarizer of single memos, a keyword search box, or a source of claims about
the world beyond what the memos say. It distinguishes **what the memos say**
(faithful) from **what is true** (true) and labels uncertainty. The evaluation is
a qualitative demonstration over 15 prompts — not statistical proof.

---

## Doc map

| File | What it covers |
|------|----------------|
| `README.md` | this file — overview + how to run |
| `ARCHITECTURE.md` | base-system design and build spec |
| `CLAUDE.md` | build constraints, relation vocab, failure modes |
| `EVALUATION_PLAN.md` | the experiment design and honesty guardrails |
| `EVALUATION_PROMPTS.md` | the 15 prompts and their (internal) reference keys |
| `EXPERIMENT_BUILD_SUMMARY.md` | what was built, step by step, and the decisions made |
| `TECHNICAL_DEEP_DIVE.md` | code-level choices and differences across the four systems |
| `eval/README.md` | the harness quick-reference |
