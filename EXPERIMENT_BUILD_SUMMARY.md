# Reno Council Memo RAG — Experiment Build Summary

A record of the four-system A/B evaluation harness built on top of the existing
Reno council-memo RAG project: what was asked, what was built, the decisions
made along the way, and how each piece was coded.

---

## Part 1 — Executive Summary

The project already had **one** working system: a research-grounded RAG over the
curated CityThread spreadsheet, with a React/FastAPI web UI (call it
**A-research**). The task was to extend it into a rigorous, blinded comparison of
**four** systems across **two experiments**, so a Reno subject-matter expert can
judge whether grounding a RAG system in published research actually changes
output quality.

| System | Experiment | Data source | Research grounding |
|--------|-----------|-------------|--------------------|
| **A-research** | A | CityThread spreadsheet (`reno.db`) | Full (already built) |
| **A-vanilla**  | A | Same spreadsheet, flattened to text | None (control) |
| **B-research** | B | Raw council PDFs | Full extraction pipeline |
| **B-vanilla**  | B | Same raw PDFs, chunked text | None (control) |

- **Experiment A** isolates the effect of grounding on *retrieval and reasoning*
  (both systems start from clean, curated data).
- **Experiment B** tests grounding on *the whole pipeline including extraction*
  (both systems start from messy raw PDFs).

The build proceeded in five stages, stopping for verification after each:
**(1)** lock an externalized contract, **(2)** build the vanilla baseline,
**(3)** build the Experiment B PDF ingestion API and both B systems, **(4)**
build the runner that executes every prompt through every system, **(5)** build a
blinded side-by-side review UI for the expert. A final fix made markdown tables
render in the UI.

The headline finding *before any expert review* was a data-integrity catch: the
spreadsheet was assumed to end **April 16, 2026**, but it actually ends **April
26**. That assumption, applied literally, would have made the two experiments
cover different time windows — the exact flaw the experiment design warns
invalidates the comparison. This was surfaced and corrected before any system ran.

Everything is wired so the **expert is the only evaluator**: there is no
automated scoring and no LLM-as-judge anywhere in the harness.

---

## Part 2 — What I Was Given

### Behavioral skill applied
- **`karpathy-guidelines`** (Andrej Karpathy coding guidelines, invoked at the
  start). Four principles drove the working style throughout: *think before
  coding / surface assumptions*, *simplicity first*, *surgical changes*, and
  *goal-driven execution*. In practice this meant stopping to ask rather than
  guessing on six genuinely ambiguous decisions (Part 4), reusing the existing
  `query.py` engine instead of rewriting it, and not "improving" the vanilla
  baseline.

### Project outlines / specs read before writing any code
- **`CLAUDE.md`** — the constraints: bounded relation vocabulary, mandatory entity
  normalization, memo-level chunking, citation requirements, known failure modes.
- **`ARCHITECTURE.md`** — the three-layer build spec (knowledge → retrieval →
  reasoning) and the intended extraction pipeline.
- **`EVALUATION_PLAN.md`** — the experiment design: four systems, what is held
  constant per pair, blinding rules, the four expert questions, honesty guardrails.
- **`EVALUATION_PROMPTS.md`** — the 15 cross-document prompts and their reference
  keys (the memos a strong answer should draw on).

### The externalized contract (provided, then filled in)
Three JSON files in `eval/` that everything reads from — no prompt text, chunk
size, or model name is hardcoded anywhere else:
- **`prompts.json`** — the locked 15-prompt set. Each prompt's `reference_key` is
  internal-only and is never sent to a system or shown to the expert.
- **`systems.config.json`** — per-system configuration (model, chunk size, top-k,
  embedding model, generic prompt, Experiment B ingestion filters).
- **`run-record.schema.json`** — the shape of each append-only run record.

---

## Part 3 — Build Steps (narrative)

**Step 1 — Lock the contract.** Filled every `FILL_FROM_EXISTING_SYSTEM`
placeholder from the *actual* A-research code (not invented values), set the
shared generation params, and created the append-only `runs/` store.

**Step 2 — A-vanilla.** A deliberately bare baseline: flatten the raw spreadsheet
rows to text → fixed 512-token chunks → local embeddings → top-8 cosine → generic
prompt. No normalization, no graph, no citations, no reranking. Confirmed it runs
end to end.

**Step 3 — Experiment B ingestion + both B systems.** Built an ingestion API that
resolves the raw PDF set from the live (bot-protected) Reno site, filters by year
and a hard date ceiling, logs every found/included/excluded memo, and fetches +
extracts the PDFs. Then built **B-vanilla** (raw-text chunks) and **B-research**
(the full extraction pipeline → self-built knowledge base). Halted mid-step to
surface the April-16-vs-26 discrepancy before anything ran.

**Step 4 — The runner.** Executes every prompt through every system, writing
verbatim, schema-conformant, append-only records with model version + config hash
+ (for B) the shared document-set hash. 60 records, zero errors.

**Step 5 — The review UI.** A blinded side-by-side comparison app: Output 1 /
Output 2 with randomized, persisted left/right order; B pairs also show the
extracted data; the four expert questions per pair; a separately-gated unblind.

**Follow-up fix.** Markdown tables in answers were rendering as raw text; added
`remark-gfm` so they render as real tables.

---

## Part 4 — Decisions Surfaced (and how they were resolved)

Per the guidelines, six genuinely ambiguous points were raised rather than
guessed. All were confirmed by the user:

1. **Generation model.** A-research's code uses `claude-sonnet-4-6`, but it was
   described as a "Haiku key." → **Keep `claude-sonnet-4-6` as-is** for all four
   (the "Haiku key" was the key's nickname, not the model).
2. **Embeddings.** The vanilla systems need an embedding model; the config named
   an OpenAI model but only an Anthropic key exists (Anthropic has no embeddings
   API). → **Local `sentence-transformers/all-MiniLM-L6-v2`** (no key, offline).
3. **Date ceiling.** The contract claimed the spreadsheet ends April 16; it
   actually ends **April 26** (8 memos dated Apr 21–26). → **Ceiling = 2026-04-26**
   so A and B cover the identical window.
4. **Restrict to the curated set.** Within that window the website lists 79 memos;
   the spreadsheet curated 77. → **Restrict B to the spreadsheet's exact 77** so A
   and B use the byte-identical document set.
5. **Generation params.** A-research as-built used `max_tokens=1500`, temperature
   default (1.0, non-deterministic); the contract said 2048 / temp 0. →
   **Standardize all four on 2048 / temp 0** (deterministic, within-pair
   symmetric); A-research's retrieval/prompt stay as built.
6. **A-research answer format.** Its router sent 10/15 eval prompts to terse
   direct-lookup dumps (breaks blinding, skips reasoning). → **Always synthesize
   prose**, feeding the curated thread/flag/metric structures into the reasoning
   layer so grounding is preserved and format stays comparable.

---

## Part 5 — Technical Appendix (per step: files, functions, approach)

### Shared infrastructure

**`eval/contract.py`** — read-only accessor for the three contract files. Every
tunable flows through here so nothing is hardcoded elsewhere.
- `get_system(id)`, `shared()`, `generation_model()` — config access.
- `prompt_text(id)` vs `reference_key(id)` — **separate functions** so the
  reference key can never accidentally be sent to a system.
- `config_hash(id)` — SHA-256 over the system's config entry + shared block
  (excluding `_comment` fields), stamped on every run record to detect config
  drift between runs.

**`eval/generate.py`** — the single Claude generation path used by all systems.
- `generate(user, system=None, max_tokens=None)` — reads model / max_tokens /
  temperature from `contract.shared()`. The `max_tokens` override exists *only*
  for B-research's internal extraction passes; the final answer generation for
  every system always uses the shared cap, keeping the comparison's generation
  params constant. Centralizing this is what makes Decision 5 enforceable.

---

### Step 1 — Lock the contract

No new module; edited **`systems.config.json`**. Filled A-research's row from the
real built system (`query.py`): `claude-sonnet-4-6`, FTS5 (no embeddings),
`memo_level` chunking, `top_k=8`. Set the vanilla embedding string to the local
MiniLM model in both vanilla rows (satisfying the pair-invariant that the two
systems in a pair share an embedding model). Replaced every `FILL_*` / `MATCH_*`
token with concrete values so the runner can hash and assert unambiguously.
Created `eval/runs/` for append-only records.

---

### Step 2 — A-vanilla (and later B-vanilla)

**`eval/vanilla_rag.py`** — one bare pipeline parameterized by `system_id`; the
only difference between A-vanilla and B-vanilla is which documents feed it.
- `load_documents(system_id)` — branches on `data_source`: `_spreadsheet_documents`
  flattens each raw Master-Log row to `"Header: value"` text (touching *only* memo
  rows — no curated threads/flags, by design); `_pdf_documents` reads the resolved
  Experiment B manifest's extracted text.
- `_chunk(text, tokenizer, chunk_size, overlap)` — fixed-size **token** chunking
  using the embedding model's own tokenizer (512 tokens, 64 overlap, from config).
- `build_index(system_id)` — embeds all chunks with `all-MiniLM-L6-v2`
  (normalized vectors) and pickles them to `eval/index/{system_id}.pkl`.
- `query(system_id, question)` — embeds the query, cosine top-8, fills the config's
  generic prompt, calls `generate()`. Returns `cited_sources=[]` (vanilla never
  cites) and an internal `retrieved_chunk_ids` for miss-detection only.

Deliberately **not** improved: the 256-token truncation that `all-MiniLM`
silently applies to the few longest chunks was left in place as authentic naive
behavior. A-vanilla → 77 chunks (one per short spreadsheet row); B-vanilla → 1,124
chunks (raw PDFs are far longer).

---

### Step 3a — Experiment B ingestion

**`eval/experiment_b_ingest.py`** — resolves, filters, fetches, logs.
- **Bypassing the block.** A bare request to the site returns Akamai 403. The page
  was *assumed* JS-rendered, but the real blocker was bot detection: sending the
  full browser header set (`sec-fetch-*`, `sec-ch-ua`, etc.) returns the memo list
  directly in the HTML. `BROWSER_HEADERS` encodes this; `_fetch()` uses stdlib
  `urllib` (no extra dependency).
- `resolve_listing(html)` — the memos live in a tabbed widget with year tabs
  (2026/2025/2024); each `<li>` is `"Month D, YYYY — <a …showpublisheddocument/ID…>
  Title</a>"`. Parses the explicit publication date per item (the `.NET` ticks in
  the URL decode to the same date, used as a cross-check).
- `classify(found)` — applies the contract filters in order: wrong year → after
  ceiling → (if enabled) not in the spreadsheet's curated set → included. Reasons
  come from the contract's `exclusion_reasons` vocabulary.
- `_spreadsheet_docset()` — reads the 77 spreadsheet `source_url` doc-ids from
  `reno.db` to drive Decision 4's restriction.
- `fetch_included()` — downloads each PDF, extracts text with `pypdf`, records
  `pdf_sha256`, writes `documents/{doc_id}.txt`; a failed fetch is recorded
  (`fetch_failed`), never silently dropped.
- `_document_set_hash()` — SHA-256 over the sorted `(doc_id, pdf_sha256)` list; the
  precondition both B systems are asserted to share.
- Outputs: `ingestion_log.json` (all 620 found memos + dispositions), `manifest.json`
  (the 77 + hash), `documents/*.txt`, `listing.html`.

**Result:** 620 found → 511 wrong-year, 30 after-cutoff, 2 not-in-spreadsheet, **77
included**, 0 fetch failures, all 77 spreadsheet memos present.

---

### Step 3b — B-research (the full extraction pipeline)

**`eval/experiment_b_research.py`** — builds a structured knowledge base from raw
PDFs, then reuses the A-research engine over it.
- `assign_global_ids(docs)` — B's own canonical `MON-###` ids by date order
  (independent of the spreadsheet's numbering).
- `extract_memo(doc)` — two LLM passes per memo, **cached** to
  `extracted/{global_id}.json`:
  1. **Coreference resolution** (separate pass, per CLAUDE.md) — `COREF_SYSTEM`
     prompt rewrites the text resolving pronouns/vague references.
  2. **Sequential typed extraction** — `EXTRACT_SYSTEM` prompt walks the entity
     types in the prescribed order (departments → projects → dollars → dates →
     people) plus the summary fields, returning strict JSON.
- `normalize_entities(records)` — the mandatory canonicalization pass.
  `NORMALIZE_SYSTEM` clusters surface-form variants into a canonical name per type
  (e.g. `CMO` → `City Manager's Office`); the registry is persisted to
  `entity_registry.json` and applied to every memo. (Output is variant *clusters*,
  not an entry per form, to stay within the token budget.)
- `extract_relations(records)` — bounded-vocabulary relations only. Candidate
  pairs share a canonical project; `same_project` edges are deterministic and an
  LLM pass (`RELATION_SYSTEM`, approved vocab only) optionally adds a directed
  edge with evidence. A missed relation is tolerated; a hallucinated one is not.
- `build_db(records, edges)` — writes `reno_b.db` with a schema **identical** to
  the A-research `reno.db` (`memos`, `relationships`, `entities`, `memos_fts`), so
  the retrieval functions work unchanged.
- `query_b(question)` — **reuses `query.py`'s `keyword_search`, `graph_walk`,
  `build_context_block`, and `SYSTEM_PROMPT`** against `reno_b.db`, generating with
  shared params. Returns `cited_sources`, `retrieved_chunk_ids`, and the
  `extracted_data` (entities / relationships / fields for the cited memos) that the
  expert inspects.

**Result:** 77 memos, registry (89 dept / 111 project / 179 people surface forms
canonicalized), 165 relationship edges. A robustness fix raised the coref token
budget and rebuilt 9 long memos whose coref had truncated.

---

### Step 4 — The runner

**`eval/runner.py`** — orchestration and append-only writes.
- `_dispatch(system_id, question)` — routes to the right system. Vanilla → 
  `vanilla_rag.query`; B-research → `query_b`; A-research → `_run_a_research`.
- `_run_a_research(question)` — implements Decision 6: runs `query.py`'s router to
  *retrieve* (threads/flags/metrics/keyword+graph), then `_render_grounding()`
  folds the curated structures into a context block and the reasoning layer
  **always** produces cited prose. `query.py` itself is untouched.
- `_build_record(...)` — assembles a schema-conformant record: `run_id` (with
  timestamp), model version, `config_hash`, `document_set_hash` for B, and the
  verbatim `output`. Asserts required fields before writing.
- `_assert_b_hash_shared()` — checks the B manifest hash exists before any B run.
- `_write(rec)` — one uniquely-named JSON file per run; re-running appends, never
  mutates.

**Result:** 60 records (15 × 4), schema-valid, 0 errors, 0 empty answers, a single
shared B document-set hash.

---

### Step 5 — The blinded review UI

**`eval/review_api.py`** (FastAPI) —
- `_latest_runs()` — latest record per (prompt, system).
- `_blind_map()` — randomizes the two systems' Output-1/Output-2 order once per
  (prompt, experiment) and **persists** it to `review/blind_map.json` (stable
  across sessions, unblindable later).
- `GET /api/prompts` — prompt text only (no reference_key).
- `GET /api/pair` — the two outputs in blind-map order; system identity never in
  the payload; `extracted_data` included only for Experiment B.
- `POST /api/response` — saves the expert's four answers, attaching the blind
  mapping so later analysis knows which system each judgment referred to.
- `POST /api/unblind` — the *only* place identity is revealed; a separate explicit
  call.

**`eval/review/`** (Vite + React 18 + react-markdown, mirroring the existing
`web/` stack) —
- `App.jsx` — prompt list, A/B toggle, two output cards (markdown answer + cited
  sources + B's collapsible extracted-data panel), the four-question form (Q4
  shown only for B), Save, and a confirm-gated Unblind.
- `remark-gfm` (the follow-up fix) renders markdown tables as real tables; matching
  table CSS added to `styles.css`.

**Verified** via API responses, production build, and the Vite→backend proxy
(not yet a rendered browser screenshot).

---

## Part 6 — How to Run

```bash
# Experiment B documents
.venv/bin/python eval/experiment_b_ingest.py

# Build indexes / knowledge bases
.venv/bin/python eval/vanilla_rag.py --build A-vanilla
.venv/bin/python eval/vanilla_rag.py --build B-vanilla
.venv/bin/python eval/experiment_b_research.py --build

# Run all prompts through all systems
.venv/bin/python eval/runner.py

# Review UI
cd eval && ../.venv/bin/uvicorn review_api:app --port 8088     # backend
cd eval/review && npm install && npm run dev                   # http://localhost:5190
```

(Full guide in `eval/README.md`.)

---

## Part 7 — Honest Caveats

- **B pairs are partially self-revealing**: only the research side shows extracted
  data (the vanilla side built none). This is inherent to Experiment B and the
  evaluation plan endorses showing it; the prose answers remain the blinded core.
- **B-research relation graph is `same_project` + `precedes` only** — the
  candidate-pair strategy (project-sharing memos) under-detects
  `depends_on`/`conflicts_with`/`funds` across unrelated-project memos. The
  reasoning layer can still infer those from content; the graph won't surface them
  via walk. This is itself a finding for the expert.
- **Coref input is capped** (~24k chars), so a couple of very long memos are
  processed from their substantive front matter, not their full tail.
- **The UI was verified via API + build + proxy**, not a rendered screenshot.
- **15 prompts is a qualitative demonstration, not statistical proof** — by design.

---

## Part 8 — File Inventory

**New code**
```
eval/contract.py              eval/generate.py
eval/vanilla_rag.py           eval/experiment_b_ingest.py
eval/experiment_b_research.py eval/runner.py
eval/review_api.py            eval/README.md
eval/review/  (package.json, vite.config.js, index.html, src/{main,App}.jsx, src/styles.css)
```
**Edited:** `eval/systems.config.json` (filled), `requirements.txt`
(sentence-transformers, numpy, pypdf).

**Generated artifacts**
```
eval/experiment_b/manifest.json, ingestion_log.json, listing.html
eval/experiment_b/documents/*.txt        (77 extracted PDF texts)
eval/experiment_b/extracted/*.json       (77 per-memo extractions, cached)
eval/experiment_b/entity_registry.json, relationships.json, reno_b.db
eval/index/{A,B}-vanilla.pkl             (embedding indexes)
eval/runs/*.json                         (60 append-only run records)
eval/review/blind_map.json, responses/*  (created on first real review)
```

**Untouched by design:** `query.py`, `ingest.py`, `api.py`, `reno.db`, and the
existing `web/` app — A-research's retrieval/reasoning engine was reused, not
modified.
