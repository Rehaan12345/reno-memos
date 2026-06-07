# Reno Council Memo RAG — Project Context

## What This Is

A RAG pipeline over Reno, NV city council memos (public open data) with a
conversational interface for pattern recognition across memos. The primary
value is cross-document reasoning — identifying patterns, tensions, and
timelines — not summarizing individual memos. Build with that distinction
in mind at every layer.

Source: https://www.reno.gov/government/city-council/memos-to-the-mayor-and-council

---

## Data Schema

The canonical data source is the CityThread spreadsheet. Field names below
match the database schema in `reno.db` exactly. Never rename these fields.

### memos table (one row per memo)
```
global_id       — canonical ID, format: JAN-001, FEB-012, etc. Primary key.
month           — Jan / Feb / Mar / Apr
memo_id         — integer memo number within the month
date_published  — ISO date string
title           — full memo title as published
department      — originating department (normalized)
authors         — author name(s)
category        — normalized category from 07 · Category Key sheet
subcategory     — second-level category
tldr            — plain-language summary, 2-4 sentences
key_stats       — quantitative facts extracted from memo
key_decisions   — decisions made or recommended
action_items    — next steps with owners and deadlines if named
keywords        — tag list
source_url      — URL to published PDF
```

### Additional tables
```
relationships   — typed edges: source_id → target_id with rel_type
threads         — 12 pre-built issue threads with monthly summaries
flags           — 10 escalation signals with priority and next step
decisions       — 14 extracted decisions with date, maker, impact
metrics         — 18 time-series (periods + data_values as JSON arrays)
```

All text fields use None for absent content. Never invent content.
global_id is the canonical reference across all tables and in all output.

---

## Architecture: Three Layers

### 1. Knowledge Layer
- Structured memo metadata (schema above)
- `memo_relationships` table linking memo_ids with typed relation edges
- Entity registry for normalized department/person/project names

### 2. Retrieval Layer
- Multi-stage retrieval: filter by metadata first, then semantic search
- Never return raw chunk text as a final answer — always synthesize
- Retrieval must return supporting memo_ids for every claim

### 3. Reasoning Layer
- Structured prompting that directs the LLM to identify patterns, tensions,
  gaps, and timelines across memos — not to summarize individual ones
- Every response must cite memo_ids as evidence
- Distinguish between what the memos say (faithful) and what is true in the
  world (true) — do not conflate these

---

## Chunking Rules

**Never chunk below a full memo section.**

Cross-sentence and cross-paragraph reasoning is required to extract
relations between departments, decisions, and deadlines. Sentence-level or
paragraph-level chunking will cause the majority of cross-document patterns
to be missed. The minimum unit of chunking is a complete logical section of
a memo. For relation extraction specifically, process the full memo text as
a single unit where possible.

---

## Entity Normalization Rules

Run a canonicalization pass before any entity or relation extraction.
Surface-form variations must be resolved to a canonical name before
building any graph or index.

Examples of what must be unified:
- "Public Works," "PW," "PW Department," "the department" → `Public Works`
- "City Manager's Office," "CMO," "the Manager" → `City Manager's Office`
- "Reno City Council," "the Council," "Council members" → `City Council`

**Never treat surface-form variations as distinct entities.** Failure to
normalize before extraction causes graph fragmentation and false negatives
in relation detection. This is the primary source of missed relations —
more so than wrong predictions.

Build and maintain an entity registry. Add new canonical forms as they are
encountered. The registry is a project artifact, not a runtime inference.

---

## Relation Extraction Rules

### Use a bounded relation vocabulary

Do not allow free-form relation labels. The LLM must not invent relation
types. Use only the approved set below. Add new types only with explicit
approval and update this file.

**Approved relation types:**
```
funds             — memo A allocates budget to item/project in memo B
authorizes        — memo A grants approval for action in memo B
depends_on        — memo A's action requires completion of item in memo B
same_project      — memo A and memo B concern the same named project
references        — memo A explicitly cites memo B
precedes          — memo A's decision logically or temporally precedes memo B
assigned_to       — action/decision in memo A is owned by entity in memo B
conflicts_with    — memo A's recommendation contradicts memo B's recommendation
```

### Extraction prompt structure

Use structured prompts with explicit entity type definitions. Extract
entity types sequentially — do not attempt joint extraction of all types
simultaneously. Recommended order:

1. Departments and offices
2. Named projects and programs
3. Dollar amounts and budget items
4. Dates and deadlines
5. Named individuals and roles
6. Relations between the above

Sequential extraction reduces attention drift and misclassification.
Open-ended joint extraction produces noisy, unreliable output.

### Coreference resolution

Run coreference resolution as a separate pass **before** relation extraction.
Do not combine these steps. Coreference resolution resolves which mentions
refer to the same entity. Relation extraction then operates on the resolved
text. Combining them degrades both.

---

## Evaluation Framework

### What to measure at each layer

**Retrieval quality** — conventional metrics (precision@k, recall@k).
Has ground truth. Measure this first.

**Relation extraction** — precision and recall against a human-annotated
reference set. Track false negatives separately from false positives.
Entity name variation is the primary cause of false negatives.

**Generation faithfulness** — does the output follow from the source memos?
Use entailment-checking against retrieved memo text. This is proxy ground
truth, not true ground truth.

**Insight value** — is the output non-obvious, grounded, correct, and
actionable? No computational ground truth exists. Requires structured human
evaluation with a rubric.

### Rubric for insight evaluation (human eval)

Rate each generated insight on four axes, 1-3 scale:
- **Grounded**: supported by specific memo_ids with traceable evidence
- **Correct**: accurate representation of what the memos say
- **Non-obvious**: not retrievable by a simple keyword search
- **Actionable**: useful to a staff member or informed citizen

### Do not trust LLM-as-judge without calibration

Any LLM-based evaluation must be calibrated against human labels before
being used as a signal. LLM judges have systematic biases. Use RAGAS,
TruLens, or DeepEval for generation faithfulness only — not for insight
value.

---

## What This System Is NOT For

- Summarizing individual memos (use the memo summary field directly)
- Answering questions resolvable by keyword search
- Making claims about the world beyond what the memos contain
- Replacing human judgment on policy questions

If a query can be answered by reading one memo, the system should return
that memo directly, not synthesize across documents.

---

## Public-Facing Design Constraints

This is open data. There are no data sensitivity concerns. The interface
should be designed for both public users and city staff.

- Plain-language output only — no jargon, no raw field names exposed
- Every claim must be traceable to a specific memo (cite memo_id and title)
- Do not present LLM-generated content as authoritative fact
- Label uncertainty explicitly when it exists

---

## Stack Decisions

```
Database:         SQLite — memos, relationships, threads, flags, decisions, metrics
Full-text search: SQLite FTS5 virtual table over search_text
Retrieval:        Keyword (FTS5) + one-hop relationship graph walk
LLM (inference):  Claude (claude-sonnet-4-6 or later)
Embedding:        Deferred — FTS5 sufficient for current dataset size
Framework:        Python scripts — no framework until CLI is validated
Deployment:       Local CLI — web layer deferred
```

Query flow: natural language → stop-word filter → FTS5 → top memos →
one-hop relationship expansion → context block → Claude reasoning layer.

Decisions deferred and why are documented in ARCHITECTURE.md.

---

## Coding Conventions

- All memo_ids are the canonical reference — never use title strings as keys
- All entity names in code and storage must be the canonical form from the
  entity registry, not raw extracted strings
- Every function that queries memos must return source memo_ids alongside
  content — never return unsourced claims
- Tests must cover entity normalization edge cases explicitly
- Do not hardcode department names as strings in logic — use the registry

---

## Key Failure Modes to Anticipate

These are known problems from the research this project is grounded in.
Build mitigations in from the start, not as patches.

1. **Entity variation causing false negatives** — same entity, different
   surface forms, treated as different entities. Mitigation: entity registry
   and mandatory normalization pass.

2. **Cross-chunk relation breakdown** — relations that span chunk boundaries
   are missed. Mitigation: memo-level chunking for relation extraction.

3. **Hallucinated relations** — LLM invents plausible but unsupported
   relation edges. Mitigation: bounded relation vocabulary, evidence-grounded
   extraction prompts, human spot-check on relation graph.

4. **Insight ≠ retrieval confusion** — system returns rephrased retrieved
   text rather than synthesized cross-document patterns. Mitigation:
   reasoning-layer prompts must explicitly instruct the LLM to identify
   patterns and tensions, not describe individual memos.

5. **Coreference noise** — LLM conflates distinct entities or fails to
   unify coreferent mentions. Mitigation: type-aware sequential coreference
   resolution before extraction.

6. **Graph fragmentation from skipping normalization** — duplicate nodes for
   the same department or project break graph-based pattern detection.
   Mitigation: normalization is mandatory, not optional.

---

## Research Rationale

Architecture decisions in this file are grounded in the following sources.
See `/docs/research-rationale.md` for the full mapping.

- Yao et al. (2019) DocRED — cross-sentence relation extraction at document level
- Meng et al. (2024) — entity name variation as primary source of false negatives
- Meher & Domeniconi (2025) CORE-KG — coreference resolution and structured
  prompting as complementary, non-substitutable components
- Zhao et al. (2024) RE Survey — bounded vocabularies for narrow-domain extraction