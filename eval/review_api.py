"""
review_api.py — FastAPI backend for the blinded side-by-side comparison UI.

Serves the run records produced by runner.py as BLINDED pairs:
  - For each (prompt, experiment) the two systems are shown as "Output 1" /
    "Output 2"; the left/right order is randomized once and persisted in
    blind_map.json so it is stable across sessions and can be unblinded later.
  - System identity is NEVER included in the pair payload. It is only returned
    by the explicit, separate /api/unblind endpoint.
  - The prompt's reference_key is never exposed.

There is NO automated scoring here. The expert is the only evaluator; this
backend just stores their structured judgments.

Run:
    ./.venv/bin/uvicorn review_api:app --reload --port 8088   # from eval/
The Vite dev server (eval/review) proxies /api to this port.
"""

import glob
import json
import random
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import contract

REVIEW_DIR = contract.EVAL_DIR / "review"
RESPONSES_DIR = REVIEW_DIR / "responses"
BLIND_MAP_PATH = REVIEW_DIR / "blind_map.json"

PAIR_SYSTEMS = {
    "A": ["A-research", "A-vanilla"],
    "B": ["B-research", "B-vanilla"],
}

# The other axis of the 2x2: fix the grounding, vary the data source. These are
# UNBLINDED inspection views, not part of the judged experiment — no blind map,
# no expert form, no saved responses.
COMPARE_SYSTEMS = {
    "research": ["A-research", "B-research"],
    "vanilla": ["A-vanilla", "B-vanilla"],
}

app = FastAPI(title="Reno RAG — Blinded Comparison Review")
app.add_middleware(
    CORSMiddleware, allow_origins=["http://localhost:5190", "http://127.0.0.1:5190"],
    allow_methods=["*"], allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Run records — latest per (prompt, system)
# --------------------------------------------------------------------------- #
def _latest_runs():
    latest = {}
    for f in glob.glob(str(contract.RUNS_DIR / "*.json")):
        r = json.loads(Path(f).read_text())
        key = (r["prompt_id"], r["system_id"])
        if key not in latest or r["timestamp"] > latest[key]["timestamp"]:
            latest[key] = r
    return latest


def _output_for(runs, prompt_id, system_id):
    rec = runs.get((prompt_id, system_id))
    if not rec:
        raise HTTPException(404, f"no run record for {prompt_id} x {system_id}")
    return rec["output"]


# --------------------------------------------------------------------------- #
# Blind map — randomized once, persisted
# --------------------------------------------------------------------------- #
def _blind_map():
    """{prompt_id: {experiment: [system_for_output1, system_for_output2]}}."""
    if BLIND_MAP_PATH.exists():
        return json.loads(BLIND_MAP_PATH.read_text())
    rng = random.Random()  # fresh randomness; persisted so it stays fixed
    bm = {}
    for p in contract.load_prompts():
        bm[p["id"]] = {}
        for exp, systems in PAIR_SYSTEMS.items():
            order = systems[:]
            rng.shuffle(order)
            bm[p["id"]][exp] = order
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    BLIND_MAP_PATH.write_text(json.dumps(bm, indent=2))
    return bm


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@app.get("/api/prompts")
def prompts():
    # Prompt text only — never the reference_key.
    return [{"id": p["id"], "section": p["section"], "prompt": p["prompt"]}
            for p in contract.load_prompts()]


@app.get("/api/pair")
def pair(prompt_id: str, experiment: str):
    if experiment not in PAIR_SYSTEMS:
        raise HTTPException(400, "experiment must be 'A' or 'B'")
    runs = _latest_runs()
    order = _blind_map()[prompt_id][experiment]
    outputs = []
    for i, system_id in enumerate(order, 1):
        out = _output_for(runs, prompt_id, system_id)
        outputs.append({
            "label": f"Output {i}",
            "answer": out["answer"],
            "cited_sources": out.get("cited_sources", []),
            # extracted_data shown for Experiment B so the expert can inspect it.
            "extracted_data": out.get("extracted_data") if experiment == "B" else None,
        })
    prompt = next(p for p in contract.load_prompts() if p["id"] == prompt_id)
    saved = _load_response(prompt_id, experiment)
    return {"prompt_id": prompt_id, "experiment": experiment,
            "prompt": prompt["prompt"], "outputs": outputs, "saved_response": saved}


@app.get("/api/compare")
def compare(prompt_id: str, axis: str):
    """Unblinded side-by-side of the same grounding across data sources
    (A-research vs B-research, or A-vanilla vs B-vanilla). Inspection only."""
    if axis not in COMPARE_SYSTEMS:
        raise HTTPException(400, "axis must be 'research' or 'vanilla'")
    runs = _latest_runs()
    outputs = []
    for system_id in COMPARE_SYSTEMS[axis]:
        out = _output_for(runs, prompt_id, system_id)
        outputs.append({
            "label": system_id,  # unblinded — system identity is the whole point here
            "answer": out["answer"],
            "cited_sources": out.get("cited_sources", []),
            "extracted_data": out.get("extracted_data") or None,
        })
    prompt = next(p for p in contract.load_prompts() if p["id"] == prompt_id)
    return {"prompt_id": prompt_id, "axis": axis,
            "prompt": prompt["prompt"], "outputs": outputs}


class ExpertResponse(BaseModel):
    prompt_id: str
    experiment: str
    more_accurate: str | None = None       # "Output 1" | "Output 2" | "Tie"
    accuracy_reason: str | None = None
    wrong_output1: str | None = None
    wrong_output2: str | None = None
    invents_output1: str | None = None
    invents_output2: str | None = None
    extraction_output1: str | None = None  # Experiment B only
    extraction_output2: str | None = None


def _response_path(prompt_id, experiment):
    return RESPONSES_DIR / f"{prompt_id}__{experiment}.json"


def _load_response(prompt_id, experiment):
    p = _response_path(prompt_id, experiment)
    return json.loads(p.read_text()) if p.exists() else None


@app.post("/api/response")
def save_response(resp: ExpertResponse):
    RESPONSES_DIR.mkdir(parents=True, exist_ok=True)
    # Store the blind mapping alongside the answers so later analysis knows which
    # system each judgment referred to — without unblinding the expert now.
    order = _blind_map()[resp.prompt_id][resp.experiment]
    record = resp.model_dump()
    record["blind_mapping"] = {"Output 1": order[0], "Output 2": order[1]}
    _response_path(resp.prompt_id, resp.experiment).write_text(json.dumps(record, indent=2))
    return {"saved": True}


@app.post("/api/unblind")
def unblind(prompt_id: str, experiment: str):
    """Explicit, separate reveal. Never called by the default pair view."""
    order = _blind_map()[prompt_id][experiment]
    return {"prompt_id": prompt_id, "experiment": experiment,
            "mapping": {"Output 1": order[0], "Output 2": order[1]}}
