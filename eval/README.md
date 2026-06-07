# Evaluation Harness — A/B × research/vanilla

Compares four RAG systems on a locked prompt set, with a blinded expert-review UI.
Everything reads from the externalized contract; nothing is hardcoded.

| System | Experiment | Data source | Grounding |
|--------|-----------|-------------|-----------|
| A-research | A | spreadsheet (`reno.db`) | full (CLAUDE.md + ARCHITECTURE.md) |
| A-vanilla  | A | spreadsheet rows | none |
| B-research | B | raw 2026 PDFs ≤ Apr 26 | full extraction pipeline |
| B-vanilla  | B | raw PDF text | none |

## The contract (do not hardcode around it)
- `prompts.json` — locked prompt set. `reference_key` is internal only; never sent to a system or shown to the expert.
- `systems.config.json` — per-system config (model, chunk size, top_k, embedding model, generic prompt, B ingestion filters).
- `run-record.schema.json` — shape of each append-only record in `runs/`.

## Pipeline
```bash
# from repo root, using the project venv

# 1. Experiment B document set (resolve + fetch + log; restricted to spreadsheet's 77)
.venv/bin/python eval/experiment_b_ingest.py            # --dry-run to classify without fetching

# 2. Build the systems' indexes / knowledge bases
.venv/bin/python eval/vanilla_rag.py --build A-vanilla
.venv/bin/python eval/vanilla_rag.py --build B-vanilla
.venv/bin/python eval/experiment_b_research.py --build  # cached per-memo; --rebuild to force
# (A-research uses the existing reno.db via query.py — nothing to build)

# 3. Run every prompt through every system (append-only -> runs/)
.venv/bin/python eval/runner.py                         # or --prompt P01 / --system A-vanilla
```

## Blinded review UI
```bash
# backend (from eval/)
cd eval && ../.venv/bin/uvicorn review_api:app --reload --port 8088
# frontend (separate shell, from eval/review/)
cd eval/review && npm install && npm run dev            # http://localhost:5190
```
- Pick a prompt, toggle Experiment A / B, judge the two blinded outputs, **Save**.
- Left/right order is randomized once and persisted in `review/blind_map.json`.
- Experiment B also shows the structured data each system built (entities / relationships / fields).
- **Unblind** is a separate, confirm-gated action; system identity is never shown by default.
- Expert answers save to `review/responses/{prompt}__{experiment}.json` with the blind mapping attached.

## Notes
- All four systems generate with the shared params in `systems.config.json` (claude-sonnet-4-6, 2048, temp 0).
- B's two systems consume the byte-identical document set; the runner asserts a single shared `document_set_hash`.
- No automated scoring or LLM-as-judge anywhere. The expert is the only evaluator.
