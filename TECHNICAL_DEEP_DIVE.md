# Technical Deep-Dive — Code Choices Across the Four Systems

This document explains, at the code level, how each of the four systems is built,
where they diverge, and *why* each choice was made. It complements
`EXPERIMENT_BUILD_SUMMARY.md` (which is the narrative): this one is the
implementation reference.

The governing constraint is the experiment design: **within a pair
(research vs vanilla), the only thing allowed to vary is research grounding.**
Everything else — model, generation params, the question text, the document set —
is held constant. So most "code choices" are really decisions about *where the
single permitted divergence lives* and how to keep everything around it identical.

---

## 0. Shared Scaffolding (identical for all four)

Three pieces sit underneath every system so that the held-constant guarantees are
enforced in code, not by convention.

### 0.1 `contract.py` — the only source of tunables
No system hardcodes a chunk size, model name, prompt, or top-k. They all read
from `systems.config.json` through `contract.py`. This is what makes the
held-constant claim auditable: e.g. `config_hash(system_id)` is a SHA-256 over a
system's config entry plus the shared block, stamped on every run record — if a
tunable changed between runs, the hash changes.

A deliberate API split:
```python
prompt_text(prompt_id)    # the only thing ever sent to a system
reference_key(prompt_id)  # internal miss-detection; defined but never called by the harness
```
Two functions instead of one field access, so the reference key cannot leak into
a systems-facing path by accident.

### 0.2 `generate.py` — one generation path for all four
```python
def generate(user, system=None, max_tokens=None):
    sh = contract.shared()                 # model, max_tokens, temperature
    ... messages=[{"role":"user","content":user}] ...
    if system: kwargs["system"] = system
```
Every final answer — vanilla or research, A or B — is produced by this one
function with the shared params (`claude-sonnet-4-6`, `max_tokens=2048`,
`temperature=0`). Centralizing it is what enforces **Decision 5** (standardized
generation). The `max_tokens` override exists *only* for B-research's internal
extraction passes; the comparison's answer generation never overrides it.

The single difference this function exposes between system *types*:
- **vanilla** calls `generate(prompt)` → no system prompt, just the generic
  "answer from the context" instruction stuffed with chunks.
- **research** calls `generate(user, system=SYSTEM_PROMPT)` → the structured
  reasoning prompt (cite global_ids, find patterns/tensions, separate faithful
  from true, label uncertainty).

### 0.3 The held-constant matrix

| Held constant within a pair | A pair | B pair |
|---|---|---|
| Generation model | sonnet-4-6 | sonnet-4-6 |
| max_tokens / temperature | 2048 / 0 | 2048 / 0 |
| Prompt text sent | identical | identical |
| Document set | `reno.db` memos | `manifest.json` (hash-asserted) |
| Embedding model (vanilla side) | MiniLM | MiniLM |
| chunk_size / overlap / top_k (vanilla side) | 512 / 64 / 8 | 512 / 64 / 8 |

The **only** intended divergence inside each pair is everything downstream of
"how the documents are turned into retrievable knowledge and prompted."

---

## 1. Experiment A — Structured Spreadsheet

Both A systems start from the *same* curated data (`reno.db`, built from the
CityThread spreadsheet by the pre-existing `ingest.py`). The divergence is purely
**retrieval + reasoning**.

### 1.1 A-research — reuse the existing engine, standardize only generation
A-research is the system that already existed. Its retrieval/reasoning lives in
`query.py` and is **not modified**. The runner wraps it (`runner._run_a_research`):

1. **Route** via `query.route()` — the research router inspects the query and
   picks a path:
   - flag-intent words → `flags` table
   - quantitative-intent + a strong series-name match → `metrics`
   - a strongly-named issue thread → `threads`
   - otherwise → `keyword_search` (FTS5, stop-words stripped, OR matching, LIMIT 8)
     followed by a **one-hop `graph_walk`** over the `relationships` table.
2. **Build context** — `_render_grounding()` folds whatever curated structure the
   router surfaced (thread signal / flag priority+next-step / metric series) into
   text, and `query.build_context_block()` formats the constituent memos
   (global_id, date, dept, tldr, key_stats, key_decisions, action_items; top 12).
3. **Always reason** — `generate(user_msg, system=query.SYSTEM_PROMPT)`.

**Why the wrapper instead of `query.answer()`?** This is **Decision 6**. The
as-built router answers ~10/15 eval prompts with a *terse direct-lookup dump*
(e.g. `Parking Revenue Recovery [Active] / Signal:… / Memos:…`), which (a) lets
the expert identify A-research by format alone — breaking blinding — and (b)
never exercises the reasoning layer the experiment is about. The wrapper keeps the
*retrieval* exactly as built (so the grounding advantage — threads/flags/metrics +
the relationship graph — is fully preserved and enters the prompt) but routes the
final step through the reasoning layer for every prompt. `query.py` is untouched;
the behavior change lives only in the runner adapter.

### 1.2 A-vanilla — deliberately bare
`vanilla_rag.py` with the spreadsheet loader:

1. **Flatten** — `_spreadsheet_documents()` reads the *raw* Master-Log rows and
   joins each memo's cells as `"Header: value"` lines. It touches **only memo
   rows** — never the curated `threads`/`flags`/`metrics`/`relationships` tables.
   That asymmetry *is* the grounding difference.
2. **Chunk** — `_chunk()` tokenizes with the embedding model's own tokenizer and
   slides a 512-token window with 64-token overlap (config-driven). Spreadsheet
   rows are short, so this yields **77 chunks** (≈ one per memo).
3. **Embed** — `all-MiniLM-L6-v2`, normalized vectors, pickled to
   `eval/index/A-vanilla.pkl`.
4. **Retrieve** — embed the query, cosine = dot product of normalized vectors,
   `argsort` top-8.
5. **Generate** — fill the config's generic prompt, `generate(prompt)` (no system
   prompt). Returns `cited_sources=[]` (vanilla never cites) and an internal
   `retrieved_chunk_ids` for private miss-detection only.

Explicitly **not** added: normalization, graph, bounded vocab, thread/flag
awareness, citations, reranking, structured reasoning prompt. Improving the
control silently turns it into a second treatment.

### 1.3 Where A-research and A-vanilla diverge in code

| Stage | A-research | A-vanilla |
|---|---|---|
| Input unit | curated memo fields + threads/flags/metrics/graph | raw flattened memo rows only |
| Index | FTS5 over `search_text` + relationship graph | MiniLM vectors over 512-tok chunks |
| Retrieval | router → direct lookup / keyword + 1-hop graph | cosine top-8 |
| Prompt | `SYSTEM_PROMPT` (cite, synthesize, faithful≠true) | generic "answer from context" |
| Citations | `global_id` + title + url | none |
| Generation | `generate(..., system=SYSTEM_PROMPT)` | `generate(prompt)` |

---

## 2. Experiment B — Raw PDFs

Both B systems consume the **byte-identical** resolved PDF set. The divergence is
the *entire pipeline*, including extraction.

### 2.1 Shared ingestion (`experiment_b_ingest.py`)
Run once; both B systems read its output.
- **Akamai bypass** — the page is bot-protected, not (as assumed) JS-rendered.
  `BROWSER_HEADERS` (full `sec-fetch-*` / `sec-ch-ua` set) makes the server return
  the memo list in-HTML; `_fetch()` uses stdlib `urllib`.
- **Resolve** — `resolve_listing()` parses the year-tab widget; each `<li>` gives
  an explicit publication date + `showpublisheddocument/{id}` URL.
- **Classify** — `classify()` applies contract filters in order: wrong year →
  after ceiling → not in the spreadsheet's 77 → included.
- **Fetch + extract** — `pypdf` text; `pdf_sha256` per file.
- **Hash** — `_document_set_hash()` over sorted `(doc_id, pdf_sha256)`; the
  precondition both B systems are asserted to share (`runner._assert_b_hash_shared`).

Output: `manifest.json` (77 docs + hash) and `documents/{doc_id}.txt`.

### 2.2 B-vanilla — same vanilla pipeline, different documents
B-vanilla is **the same `vanilla_rag.py` code path as A-vanilla**. The single
change is the document loader:
```python
_pdf_documents()  # reads manifest.json -> documents/*.txt (raw extracted PDF text)
```
Because raw PDFs are far longer than spreadsheet rows, the identical 512/64
chunker produces **1,124 chunks** (vs A-vanilla's 77). Everything else — embedding
model, top-8 cosine, generic prompt, no citations — is byte-for-byte the same
function. This is intentional: A-vanilla vs B-vanilla isolates the effect of
*source data shape* on a fixed pipeline.

### 2.3 B-research — build a knowledge base from scratch
`experiment_b_research.py` is the heart of the experiment: it reconstructs, from
raw PDFs, the kind of structure the spreadsheet handed A-research for free.

**Pipeline (per CLAUDE.md / ARCHITECTURE.md), cached to `extracted/{id}.json`:**

1. `assign_global_ids()` — B's own `MON-###` ids by date (independent of the
   spreadsheet's numbering — so e.g. parking is `JAN-002` here vs `JAN-003` in A).
2. **Coreference** (separate pass) — `generate(raw[:24000], COREF_SYSTEM,
   max_tokens=8192)` resolves pronouns/vague references. Kept separate from
   extraction because CLAUDE.md mandates it ("do not combine these steps").
3. **Sequential typed extraction** — `generate(resolved[:18000], EXTRACT_SYSTEM,
   max_tokens=4096)` walks entity types *in order* (departments → projects →
   dollars → dates → people) then the summary fields, returning strict JSON.
   Sequential (not joint) to reduce attention drift.
4. **Normalization** — `normalize_entities()` runs one clustering call per type
   (`NORMALIZE_SYSTEM`), producing a surface→canonical map persisted to
   `entity_registry.json`, then applied to every memo. Output is variant
   *clusters* (`{canonical: [variants]}`), not an entry per form, to fit the token
   budget; a parse failure falls back to an identity map rather than crashing.
   This is the mandated defense against entity-variation false negatives.
5. **Bounded-vocabulary relations** — `extract_relations()` considers memo pairs
   sharing a canonical *project*; emits a deterministic `same_project` edge and
   asks `RELATION_SYSTEM` (approved vocab only) for an optional directed edge with
   evidence. A missed relation is tolerated; a hallucinated one is rejected by
   construction (vocab is bounded).
6. `build_db()` — writes `reno_b.db` with a schema **identical** to A-research's
   `reno.db` (`memos`, `relationships`, `entities`, `memos_fts`), so the existing
   retrieval functions work over it unchanged.

**Retrieval + reasoning** (`query_b`): this is the key reuse decision — it calls
**`query.keyword_search`, `query.graph_walk`, `query.build_context_block`, and
`query.SYSTEM_PROMPT`** against `reno_b.db`. So B-research and A-research share the
*identical* retrieval+reasoning engine; the only difference between them is whether
the knowledge base was human-curated (A) or self-extracted from PDFs (B). That is
exactly the contrast Experiment B is meant to isolate.

`query_b` additionally returns `extracted_data` — the entities, relationships, and
fields behind the cited memos — so the expert can inspect extraction quality, per
EVALUATION_PLAN.

### 2.4 Where B-research and B-vanilla diverge in code

| Stage | B-research | B-vanilla |
|---|---|---|
| Extraction | coref → sequential typed → normalized registry | none |
| Knowledge store | `reno_b.db` (memos + graph + entities + FTS) | MiniLM vectors over 512-tok chunks |
| Retrieval | FTS5 keyword + 1-hop graph (reused `query.py`) | cosine top-8 |
| Prompt | `SYSTEM_PROMPT` | generic |
| Citations / structure | global_ids + `extracted_data` | none |

---

## 3. Cross-Experiment Differences (A vs B, same grounding)

Holding *grounding* fixed and varying the *experiment* isolates the effect of
clean-vs-raw source data:

- **research:** A-research **inherits** a curated KB (zero extraction); B-research
  **builds** one with an LLM pipeline (coref/extraction/normalization/relations).
  Same retrieval+reasoning engine on top. The quality gap between the curated and
  self-built KBs is what Experiment B exposes.
- **vanilla:** identical pipeline, but A-vanilla embeds 77 short structured rows
  while B-vanilla embeds 1,124 chunks of long raw PDF prose. Same code, very
  different retrieval surface.

---

## 4. The Divergence Map (one table, all four)

| Pipeline stage | A-research | A-vanilla | B-research | B-vanilla |
|---|---|---|---|---|
| **Source** | `reno.db` (curated) | spreadsheet rows | raw PDFs | raw PDFs |
| **Extraction** | inherited (none) | none | coref + sequential + normalize + relations | none |
| **Unit / chunk** | whole memo (FTS) | 512-tok / 64 | whole memo (FTS) | 512-tok / 64 |
| **Index** | FTS5 + graph | MiniLM cosine | FTS5 + graph (`reno_b.db`) | MiniLM cosine |
| **Retrieval** | router + 1-hop graph | top-8 cosine | keyword + 1-hop graph | top-8 cosine |
| **Reasoning prompt** | `SYSTEM_PROMPT` | generic | `SYSTEM_PROMPT` | generic |
| **Citations** | yes | no | yes + `extracted_data` | no |
| **Generation** | shared 2048/0 | shared 2048/0 | shared 2048/0 | shared 2048/0 |
| **Code module** | `query.py` + runner adapter | `vanilla_rag.py` | `experiment_b_research.py` (reuses `query.py`) | `vanilla_rag.py` |

Reading the table by row shows what's held constant (Generation); reading by
column shows each system's stack. The vanilla columns are identical code; the
research columns share an engine but differ in how the KB was produced.

---

## 5. Specific Code-Choice Rationales

- **Token-based chunking via the embedding model's own tokenizer** (not characters
  or words): "512 tokens" in the config is honored exactly, and chunk boundaries
  align with what the embedder actually sees.
- **Per-document chunking** (not concatenate-then-split): preserves memo
  boundaries, the industry-default behavior for naive RAG. With short spreadsheet
  rows this means one chunk per memo — left as-is rather than "fixed," because
  tuning the baseline is forbidden.
- **Reusing `query.py` for B-research via schema compatibility**: writing
  `reno_b.db` with the same table/column names lets `keyword_search` /
  `graph_walk` / `build_context_block` run unchanged. This guarantees A-research
  and B-research share an identical retrieval+reasoning layer — the cleanest way
  to ensure the only A/B-research difference is the KB's origin.
- **Caching per-memo extraction** to JSON: the ~150-call pipeline runs once;
  re-runs and targeted rebuilds (e.g. the 9 long memos whose coref truncated) are
  cheap and don't re-spend the budget.
- **Cluster-format normalization** (`{canonical:[variants]}`, omit singletons):
  keeps the output within `max_tokens` and is the only reason the normalization
  pass is feasible over 100+ surface forms in a single call per type.
- **`same_project` deterministic + one LLM directed-relation call per pair**:
  grounds the graph in shared entities while keeping the directed edges
  evidence-checked and vocab-bounded — never free-form (mitigates hallucinated
  relations).
- **Centralized `generate()` + `max_tokens` override scoped to extraction**: the
  comparison's answer generation is provably constant; only B-research's internal
  passes (which need long output) deviate, and never on the answer.
- **A-research prose synthesis in the runner, not in `query.py`**: preserves the
  shipped system while making the eval output comparable and blindable.
- **Persisted blind map**: randomize once, store, so left/right is stable across
  sessions and unblindable later — blinding that survives a page reload.

---

## 6. Artifacts Each System Produces

- **A-vanilla / B-vanilla** → `eval/index/{id}.pkl`:
  `{chunks, chunk_ids, embeddings (np.ndarray), embedding_model, chunk_size,
  overlap, n_docs}`.
- **B-research** → `reno_b.db` (memos/relationships/entities/memos_fts),
  `entity_registry.json` (surface→canonical per type),
  `relationships.json` (edges with evidence), `extracted/{id}.json` (per-memo
  resolved text + typed entities + fields).
- **Every system, every prompt** → one append-only `eval/runs/*.json` record:
  `run_id, prompt_id, system_id, experiment, timestamp,
  generation_model_version, config_hash, document_set_hash (B only),
  output{answer, cited_sources, extracted_data, retrieved_chunk_ids}, error`.

---

## 7. CLAUDE.md Failure Modes → Where They're Mitigated in Code

| Failure mode (CLAUDE.md) | Mitigation in this build |
|---|---|
| Entity variation → false negatives | `normalize_entities()` + persisted registry (B-research) |
| Cross-chunk relation breakdown | memo-level units for FTS/extraction (research side) |
| Hallucinated relations | bounded `APPROVED_RELATIONS`, evidence-grounded, "none" allowed |
| Insight ≠ retrieval | `SYSTEM_PROMPT` forces synthesis, not restatement (research side) |
| Coreference noise | separate coref pass before extraction (B-research) |
| Graph fragmentation | normalization is mandatory before edges are built |

The vanilla systems intentionally mitigate **none** of these — that is the point
of the control.

---

## 8. Code Excerpts (verbatim)

The core function bodies, copied from source. These are the literal divergence
points described above.

### 8.1 The one generation path — `eval/generate.py`
Every answer, all four systems, flows through here with the shared params. The
`max_tokens` override is the *only* deviation, and only B-research's extraction
uses it — never an answer.
```python
def generate(user, system=None, max_tokens=None):
    import anthropic
    sh = contract.shared()
    client = anthropic.Anthropic()
    kwargs = dict(
        model=sh["generation_model"],
        max_tokens=max_tokens or sh["max_tokens"],
        temperature=sh["temperature"],
        messages=[{"role": "user", "content": user}],
    )
    if system:                       # vanilla passes no system prompt
        kwargs["system"] = system
    resp = client.messages.create(**kwargs)
    return "".join(b.text for b in resp.content if b.type == "text")
```

### 8.2 Vanilla fixed-size token chunking — `eval/vanilla_rag.py`
Identical for A-vanilla (short rows → 77 chunks) and B-vanilla (long PDFs → 1,124
chunks). Chunks by the embedding model's own tokens, 512 window / 64 overlap.
```python
def _chunk(text, tokenizer, chunk_size, overlap):
    ids = tokenizer(text, add_special_tokens=False)["input_ids"]
    if not ids:
        return []
    step = max(1, chunk_size - overlap)
    chunks = []
    for start in range(0, len(ids), step):
        window = ids[start:start + chunk_size]
        if not window:
            break
        chunks.append(tokenizer.decode(window))
        if start + chunk_size >= len(ids):
            break
    return chunks
```

### 8.3 Vanilla retrieval + generation — `eval/vanilla_rag.py`
Cosine = dot product of normalized vectors; top-k; stuff the generic prompt; no
system prompt, no citations.
```python
def query(system_id, question):
    sysc = contract.get_system(system_id)
    idx = _load_index(system_id)
    model = _embedder(sysc["embedding_model"])

    qv = model.encode([question], normalize_embeddings=True, convert_to_numpy=True)[0]
    sims = idx["embeddings"] @ qv
    k = int(sysc["top_k"])
    top = np.argsort(-sims)[:k]

    context = "\n\n---\n\n".join(idx["chunks"][i] for i in top)
    prompt = sysc["generic_prompt"].format(context=context, question=question)
    answer = _generate(prompt)                 # -> generate(prompt), no system

    return {
        "answer": answer,
        "cited_sources": [],                   # vanilla never cites
        "extracted_data": None,
        "retrieved_chunk_ids": [idx["chunk_ids"][i] for i in top],
    }
```

### 8.4 A-research adapter — `eval/runner.py`
Retrieval/routing via the unmodified `query.py`; curated structures folded in by
`_render_grounding`; the reasoning layer always produces cited prose (Decision 6).
```python
def _run_a_research(question):
    import query
    from generate import generate

    conn = query.connect()
    try:
        result = query.route(conn, question)
        if result["route"] == "reasoning":
            memos = result["memos"][:query.MAX_CONTEXT_MEMOS]
        else:                                   # threads/flags/metrics route
            memos = query.get_memos(conn, result.get("memo_ids", []))[:query.MAX_CONTEXT_MEMOS]

        grounding = _render_grounding(result)   # thread/flag/metric structures as text
        memo_ctx = query.build_context_block(memos) if memos else ""
        parts = []
        if grounding:
            parts.append("Curated cross-document analysis (research grounding):\n" + grounding)
        if memo_ctx:
            parts.append("Supporting memos:\n\n" + memo_ctx)
        context = "\n\n".join(parts)

        if context:
            user_msg = (
                f"Question: {question}\n\n{context}\n\n"
                "Answer the question by reasoning across these memos and the curated "
                "analysis above. Cite global_ids."
            )
            answer = generate(user_msg, system=query.SYSTEM_PROMPT)
        else:
            answer = "No memos matched this query, so there is nothing to reason over."

        cited_ids = [m["global_id"] for m in memos]
        rows = query.get_memos(conn, cited_ids)
        cited = [{"memo_id": r["global_id"], "title": r["title"],
                  "source_url": r["source_url"]} for r in rows]
        return {"answer": answer, "cited_sources": cited,
                "extracted_data": None, "retrieved_chunk_ids": cited_ids}
    finally:
        conn.close()
```

### 8.5 B-research per-memo extraction — `eval/experiment_b_research.py`
The two-pass, cached extraction: coref *then* sequential typed extraction. The
`max_tokens` overrides are the extraction-only deviation from §8.1.
```python
def extract_memo(doc, rebuild=False):
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    cache = EXTRACT_DIR / f"{doc['global_id']}.json"
    if cache.exists() and not rebuild:
        return json.loads(cache.read_text())

    # Pass 1 — coreference resolution (separate pass, before extraction).
    resolved = generate(doc["raw_text"][:24000], system=COREF_SYSTEM, max_tokens=8192)
    # Pass 2 — sequential typed extraction + fields on the resolved text.
    fields = _parse_json(generate(resolved[:18000], system=EXTRACT_SYSTEM, max_tokens=4096))

    rec = {"global_id": doc["global_id"], "month": doc["month"], "memo_id": doc["memo_id"],
           "date_published": doc["publication_date"], "title": doc["title"],
           "source_url": doc["source_url"], "doc_id": doc["doc_id"],
           "resolved_text": resolved, "fields": fields}
    cache.write_text(json.dumps(rec, indent=2))
    return rec
```

### 8.6 B-research retrieval — reuses the A engine over `reno_b.db`
`keyword_search`, `graph_walk`, `build_context_block`, `SYSTEM_PROMPT` are all
imported from `query.py`. Identical engine to A-research; only the KB differs. The
extra block assembles `extracted_data` for the expert.
```python
def query_b(question):
    conn = _connect()                                   # reno_b.db
    try:
        seeds = query.keyword_search(conn, question)
        expanded = query.graph_walk(conn, [m["global_id"] for m in seeds])
        memos = (seeds + expanded)[:query.MAX_CONTEXT_MEMOS]
        context = query.build_context_block(memos)
        user_msg = (f"Question: {question}\n\nContext block — {len(memos)} memos:"
                    f"\n\n{context}\n\nAnswer the question by reasoning across these "
                    "memos. Cite global_ids.")
        answer = generate(user_msg, system=query.SYSTEM_PROMPT) if memos else \
            "No memos matched this query, so there is nothing to reason over."

        used_ids = [m["global_id"] for m in memos]
        rels = [dict(r) for r in conn.execute(
            "SELECT source_id, target_id, rel_type, evidence FROM relationships "
            "WHERE source_id IN (%s) OR target_id IN (%s)" %
            (",".join("?" * len(used_ids)), ",".join("?" * len(used_ids))),
            used_ids + used_ids).fetchall()] if used_ids else []
        ent_rows = conn.execute("SELECT name, etype, memo_ids FROM entities").fetchall() if used_ids else []
        entities = [{"name": r["name"], "type": r["etype"],
                     "memo_ids": [g for g in json.loads(r["memo_ids"]) if g in used_ids]}
                    for r in ent_rows]
        entities = [e for e in entities if e["memo_ids"]]
        fields = {m["global_id"]: {k: m[k] for k in ("title", "department", "category",
                  "tldr", "key_stats", "key_decisions", "action_items")} for m in memos}

        return {
            "answer": answer,
            "cited_sources": [{"memo_id": m["global_id"], "title": m["title"],
                               "source_url": m["source_url"]} for m in memos],
            "extracted_data": {"entities": entities, "relationships": rels, "fields": fields},
            "retrieved_chunk_ids": used_ids,
        }
    finally:
        conn.close()
```

### 8.7 Reading 8.3 against 8.6 — the whole experiment in two functions
`query` (8.3) and `query_b` (8.6) are the clearest statement of the B pair:
- both take a raw-PDF-derived store and a question,
- `query` embeds chunks and stuffs the top-k into a generic prompt with no system
  prompt and no citations;
- `query_b` runs keyword + graph retrieval over a structured KB, reasons with
  `SYSTEM_PROMPT`, cites global_ids, and returns the `extracted_data` behind the
  answer.

Same inputs, same model, same generation params — different epistemics.
