"""
runner.py — execute the locked prompt set through every configured system and
write append-only run records to eval/runs/.

Rules (EVALUATION_PLAN + run-record.schema.json):
  - Every prompt runs through every system, verbatim. Only the `prompt` field is
    sent; the reference_key is never passed to a system.
  - Outputs are stored EXACTLY as produced. No editing, no post-processing, no
    scoring. (No system rates another system here.)
  - Append-only: each run is a uniquely-named file (run_id has a timestamp).
    Re-running adds new records; it never mutates old ones.
  - Each record stamps the generation model version and a hash of the system's
    config entry. Experiment B records the shared document_set_hash; both B
    systems are asserted to share it before any B run.

CLI:
    python eval/runner.py                         # all prompts x all systems
    python eval/runner.py --system A-vanilla       # all prompts, one system
    python eval/runner.py --prompt P01             # one prompt, all systems
    python eval/runner.py --prompt P01 --system B-research
"""

import json
import sys
from datetime import datetime, timezone

import contract

sys.path.insert(0, str(contract.ROOT))  # for query.py (A-research engine)

SYSTEM_IDS = ["A-research", "A-vanilla", "B-research", "B-vanilla"]
B_MANIFEST = contract.EVAL_DIR / "experiment_b" / "manifest.json"

# Required top-level keys in a run record (from run-record.schema.json).
_REQUIRED = {"run_id", "prompt_id", "system_id", "experiment", "timestamp",
             "generation_model_version", "config_hash", "output"}


# --------------------------------------------------------------------------- #
# System dispatch — each returns the run-record `output` shape
# --------------------------------------------------------------------------- #
def _render_grounding(result):
    """Render the curated structures the research pipeline surfaced (thread/flag/
    metric) as reasoning context, so A-research's grounding advantage enters the
    prompt even when the router matched a direct-lookup structure."""
    import query

    r, out = result["route"], []
    if r == "threads":
        for t in result["threads"]:
            ids = ", ".join(query._json(t["memo_ids"]))
            out.append(f"Issue thread '{t['name']}' [{t['status']}] — key signal: "
                       f"{t['key_signal']}; memos: {ids}")
    elif r == "flags":
        for f in result["flags"]:
            src = ", ".join(query._json(f["source_memos"])) or f.get("source_raw") or "—"
            out.append(f"Escalation flag '{f['flag']}' [{f['priority']}] — signal: "
                       f"{f['signal']}; status: {f['status']}; next step: {f['next_step']}; "
                       f"memos: {src}")
    elif r == "metrics":
        for m in result["metrics"]:
            periods, values = query._json(m["periods"]), query._json(m["data_values"])
            series = ", ".join(f"{p}={v}" for p, v in zip(periods, values))
            src = ", ".join(query._json(m["source_memo_ids"])) or "—"
            out.append(f"Metric series '{m['series_name']}' ({m['unit']}): {series}; "
                       f"memos: {src}")
    return "\n".join(out)


def _run_a_research(question):
    """
    A-research: retrieval/routing via the built research pipeline (query.py), but
    ALWAYS synthesize a cited prose answer through the reasoning layer. Curated
    structures the router surfaced (threads/flags/metrics) are fed in as grounding
    so the research advantage is preserved while the format stays comparable to
    the other systems (blinding intact). Generation uses the shared params.
    """
    import query
    from generate import generate

    conn = query.connect()
    try:
        result = query.route(conn, question)
        if result["route"] == "reasoning":
            memos = result["memos"][:query.MAX_CONTEXT_MEMOS]
        else:
            memos = query.get_memos(conn, result.get("memo_ids", []))[:query.MAX_CONTEXT_MEMOS]

        grounding = _render_grounding(result)
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


def _dispatch(system_id, question):
    if system_id == "A-research":
        return _run_a_research(question)
    if system_id in ("A-vanilla", "B-vanilla"):
        import vanilla_rag
        return vanilla_rag.query(system_id, question)
    if system_id == "B-research":
        import experiment_b_research as R
        return R.query_b(question)
    raise ValueError(f"unknown system '{system_id}'")


# --------------------------------------------------------------------------- #
# Record assembly + append-only write
# --------------------------------------------------------------------------- #
def _b_document_set_hash():
    return json.loads(B_MANIFEST.read_text())["document_set_hash"]


def _assert_b_hash_shared():
    """Both B systems consume the same manifest, so they share one doc-set hash.
    Assert it exists before any B run (the precondition for a valid B comparison)."""
    if not B_MANIFEST.exists():
        raise SystemExit("Experiment B manifest missing — run experiment_b_ingest.py first.")
    return _b_document_set_hash()


def _build_record(prompt_id, system_id, output, error=None):
    sysc = contract.get_system(system_id)
    experiment = sysc["experiment"]
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    rec = {
        "run_id": f"{prompt_id}__{system_id}__{ts}",
        "prompt_id": prompt_id,
        "system_id": system_id,
        "experiment": experiment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "generation_model_version": contract.generation_model(),
        "config_hash": contract.config_hash(system_id),
        "document_set_hash": _b_document_set_hash() if experiment == "B" else None,
        "output": {
            "answer": output.get("answer", ""),
            "cited_sources": output.get("cited_sources", []),
            "extracted_data": output.get("extracted_data"),
            "retrieved_chunk_ids": output.get("retrieved_chunk_ids"),
        },
        "error": error,
    }
    missing = _REQUIRED - set(rec)
    if missing:
        raise AssertionError(f"record missing required fields: {missing}")
    return rec


def _write(rec):
    contract.RUNS_DIR.mkdir(exist_ok=True)
    path = contract.RUNS_DIR / f"{rec['run_id']}.json"  # unique name => append-only
    path.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run(prompt_ids=None, system_ids=None):
    prompts = contract.load_prompts()
    if prompt_ids:
        prompts = [p for p in prompts if p["id"] in prompt_ids]
    systems = system_ids or SYSTEM_IDS
    if any(s.startswith("B-") for s in systems):
        _assert_b_hash_shared()

    n = 0
    for p in prompts:
        for system_id in systems:
            n += 1
            try:
                output = _dispatch(system_id, p["prompt"])  # only the prompt is sent
                rec = _build_record(p["id"], system_id, output)
                status = "ok"
            except Exception as e:
                rec = _build_record(p["id"], system_id, {}, error=f"{type(e).__name__}: {e}")
                status = f"ERROR {e}"
            path = _write(rec)
            print(f"  [{n}] {p['id']} x {system_id:11} -> {path.name}  ({status})")
    print(f"\nWrote {n} run record(s) to {contract.RUNS_DIR}")


def main():
    args = sys.argv[1:]
    prompt_ids = system_ids = None
    if "--prompt" in args:
        prompt_ids = [args[args.index("--prompt") + 1]]
    if "--system" in args:
        system_ids = [args[args.index("--system") + 1]]
    run(prompt_ids, system_ids)


if __name__ == "__main__":
    main()
