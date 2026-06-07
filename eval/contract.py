"""
contract.py — read-only access to the externalized evaluation contract.

Everything in the eval harness reads its configuration from the three locked
files in eval/ (prompts.json, systems.config.json, run-record.schema.json).
No prompt text, chunk size, model name, or generic prompt is hardcoded in any
system or in the runner — it all comes through here. If a caller needs a value
that lives in the contract, it asks this module; it does not inline a literal.

The `reference_key` field on prompts is for internal logging / miss-detection
ONLY. `prompt_text()` returns just the prompt; `reference_key()` is separate and
must never be passed to a system or rendered in an expert-facing view.
"""

import hashlib
import json
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
ROOT = EVAL_DIR.parent

SYSTEMS_CONFIG = EVAL_DIR / "systems.config.json"
PROMPTS = EVAL_DIR / "prompts.json"
RUN_SCHEMA = EVAL_DIR / "run-record.schema.json"
RUNS_DIR = EVAL_DIR / "runs"


def _load(path):
    with open(path) as f:
        return json.load(f)


# --------------------------------------------------------------------------- #
# Systems config
# --------------------------------------------------------------------------- #
def load_config():
    return _load(SYSTEMS_CONFIG)


def shared():
    """The generation parameters every system shares (model, max_tokens, temperature)."""
    return load_config()["shared"]


def get_system(system_id):
    """The raw config entry for one system, e.g. 'A-vanilla'."""
    for s in load_config()["systems"]:
        if s["id"] == system_id:
            return s
    raise KeyError(f"system '{system_id}' not found in {SYSTEMS_CONFIG.name}")


def generation_model():
    return shared()["generation_model"]


def config_hash(system_id):
    """
    Stable hash of everything that defines a system's run: its own config entry
    plus the shared generation block. Recorded with each run so a later config
    change is detectable. Keys excluded: comment/note fields (start with '_').
    """
    sys_entry = {k: v for k, v in get_system(system_id).items() if not k.startswith("_")}
    shared_block = {k: v for k, v in shared().items() if not k.startswith("_")}
    blob = json.dumps({"system": sys_entry, "shared": shared_block}, sort_keys=True)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# Prompts (locked set)
# --------------------------------------------------------------------------- #
def load_prompts():
    return _load(PROMPTS)["prompts"]


def prompt_text(prompt_id):
    """The verbatim prompt sent to a system. Never includes the reference key."""
    for p in load_prompts():
        if p["id"] == prompt_id:
            return p["prompt"]
    raise KeyError(f"prompt '{prompt_id}' not found in {PROMPTS.name}")


def reference_key(prompt_id):
    """INTERNAL ONLY — miss-detection. Never send to a system or show an expert."""
    for p in load_prompts():
        if p["id"] == prompt_id:
            return p.get("reference_key")
    raise KeyError(f"prompt '{prompt_id}' not found in {PROMPTS.name}")
