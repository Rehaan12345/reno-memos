"""
query.py — Layer 2 (Retrieval) + Layer 3 (Reasoning)

Retrieval modes (Layer 2):
  - Direct lookup     : threads / flags / metrics / decisions, no LLM
  - Keyword retrieval : FTS5 over memos.search_text, stop-words stripped, OR matching
  - Graph walk        : one-hop expansion over the relationships table

Reasoning (Layer 3):
  - Builds a citation-ready context block and calls Claude to synthesize
    cross-document patterns, tensions, timelines, and gaps — not to summarize.

Every retrieval function returns global_ids alongside content. Nothing in this
module returns memo content without its source ID (CLAUDE.md / ARCHITECTURE.md).

Library use:
    from query import answer, retrieve
Command line:
    python query.py "what's happening with parking revenue?"
    python query.py --no-llm "high priority flags"
"""

import os
import re
import sqlite3
import sys

# Load ANTHROPIC_API_KEY (and any other vars) from a local .env if present, so
# both the CLI and the API pick up the key without extra flags. Optional dep.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

DB_PATH = "reno.db"
MODEL = "claude-sonnet-4-6"
MAX_CONTEXT_MEMOS = 12  # truncate from the bottom (least relevant) past this

# Minimal English stop-word set — enough to strip filler before FTS5.
STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "for", "with",
    "at", "by", "from", "about", "as", "into", "is", "are", "was", "were", "be",
    "been", "being", "do", "does", "did", "has", "have", "had", "what", "whats",
    "which", "who", "whom", "whose", "when", "where", "why", "how", "show", "me",
    "tell", "give", "find", "list", "any", "all", "some", "this", "that", "these",
    "those", "there", "their", "them", "they", "it", "its", "we", "you", "i",
    "happening", "going", "status", "update", "updates", "over", "time",
    "whats", "going", "on", "can", "could", "would", "should", "please",
}

# Words that route a query to the flags table.
FLAG_HINTS = {"flag", "flags", "priority", "escalation", "escalating", "urgent",
              "risk", "risks", "issue", "issues", "concern", "concerns", "active"}

# Quantitative-intent words that route a query to the metrics table. These are
# about *intent* (asking for a series/trend), not domain nouns like "revenue".
METRIC_HINTS = {"trend", "trends", "rate", "count", "counts", "volume", "many",
                "much", "average", "per", "chart", "graph", "series", "data",
                "statistics", "stats", "figures", "numbers"}

# Generic words that don't make a thread/metric name distinctive.
GENERIC_NAME_WORDS = {"reno", "city", "report", "reports", "monthly", "weekly",
                      "number", "average", "program", "updates", "update"}


# --------------------------------------------------------------------------- #
# Connection
# --------------------------------------------------------------------------- #
def connect(db_path=DB_PATH):
    if not os.path.exists(db_path):
        raise SystemExit(f"Database {db_path} not found. Run: python ingest.py")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def content_words(text):
    """Lowercase tokens with stop-words removed, for FTS and routing."""
    tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
    return [t for t in tokens if t not in STOP_WORDS and len(t) > 1]


# --------------------------------------------------------------------------- #
# Direct lookup (no LLM)
# --------------------------------------------------------------------------- #
def get_memos(conn, global_ids):
    """Fetch full memo rows for a list of ids, preserving input order."""
    if not global_ids:
        return []
    placeholders = ",".join("?" for _ in global_ids)
    rows = conn.execute(
        f"SELECT * FROM memos WHERE global_id IN ({placeholders})", global_ids
    ).fetchall()
    by_id = {r["global_id"]: dict(r) for r in rows}
    return [by_id[g] for g in global_ids if g in by_id]


def lookup_threads(conn, query=None):
    """Return threads, optionally filtered by name match against the query."""
    rows = [dict(r) for r in conn.execute("SELECT * FROM threads").fetchall()]
    if not query:
        return rows
    qwords = set(content_words(query))
    scored = []
    for t in rows:
        name_words = set(content_words(t["name"]))
        overlap = len(qwords & name_words)
        if overlap:
            scored.append((overlap, t))
    scored.sort(key=lambda x: -x[0])
    return [t for _, t in scored] if scored else []


def lookup_flags(conn, priority=None):
    """Return flags, optionally filtered to a priority tier (e.g. 'High')."""
    if priority:
        rows = conn.execute(
            "SELECT * FROM flags WHERE priority LIKE ?", (f"%{priority}%",)
        ).fetchall()
    else:
        # Order High -> Medium -> Low for readability.
        rows = conn.execute(
            "SELECT * FROM flags ORDER BY CASE "
            "WHEN priority LIKE '%High%' THEN 0 "
            "WHEN priority LIKE '%Medium%' THEN 1 ELSE 2 END"
        ).fetchall()
    return [dict(r) for r in rows]


def lookup_metrics(conn, query=None):
    """Return metric series, optionally filtered by name match against the query."""
    rows = [dict(r) for r in conn.execute("SELECT * FROM metrics").fetchall()]
    if not query:
        return rows
    qwords = set(content_words(query))
    scored = []
    for m in rows:
        name_words = set(content_words(m["series_name"]))
        overlap = len(qwords & name_words)
        if overlap:
            scored.append((overlap, m))
    scored.sort(key=lambda x: -x[0])
    return [m for _, m in scored] if scored else []


def lookup_decisions(conn, category=None):
    if category:
        rows = conn.execute(
            "SELECT * FROM decisions WHERE category LIKE ?", (f"%{category}%",)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM decisions ORDER BY date").fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------- #
# Keyword retrieval + graph walk
# --------------------------------------------------------------------------- #
def keyword_search(conn, query, limit=8):
    """FTS5 search with stop-words stripped and OR matching. Returns memo rows."""
    words = content_words(query)
    if not words:
        return []
    # Quote each term to neutralize FTS5 syntax characters; OR for partial recall.
    match_expr = " OR ".join(f'"{w}"' for w in words)
    rows = conn.execute(
        "SELECT m.* FROM memos_fts f JOIN memos m ON m.global_id = f.global_id "
        "WHERE memos_fts MATCH ? ORDER BY rank LIMIT ?",
        (match_expr, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def graph_walk(conn, global_ids, exclude=None):
    """One-hop expansion: memos connected to the seed set via relationships."""
    if not global_ids:
        return []
    exclude = set(exclude or []) | set(global_ids)
    placeholders = ",".join("?" for _ in global_ids)
    # Edges are directed; treat the relationship as connective in both directions.
    rows = conn.execute(
        f"SELECT DISTINCT target_id AS nbr FROM relationships WHERE source_id IN ({placeholders}) "
        f"UNION "
        f"SELECT DISTINCT source_id AS nbr FROM relationships WHERE target_id IN ({placeholders})",
        global_ids + global_ids,
    ).fetchall()
    neighbors = [r["nbr"] for r in rows if r["nbr"] not in exclude]
    return get_memos(conn, neighbors)


# --------------------------------------------------------------------------- #
# Routing
# --------------------------------------------------------------------------- #
def route(conn, query):
    """
    Decide which retrieval path a query takes. Returns a dict:
        {"route": <name>, "memo_ids": [...], "data": {...}}
    Direct-lookup routes resolve without the LLM; the 'reasoning' route
    returns retrieved memos for synthesis.

    Order follows ARCHITECTURE.md (thread / flag / metric / keyword), but each
    direct route requires a *strong* match so generic single-word overlaps fall
    through to cross-document reasoning rather than hijacking a direct lookup.
    """
    words = set(content_words(query))

    # 1. Flags question — any flag-intent word triggers the flags table.
    if words & FLAG_HINTS:
        priority = "High" if "high" in query.lower() else None
        flags = lookup_flags(conn, priority)
        memo_ids = sorted({g for f in flags for g in _json(f["source_memos"])})
        return {"route": "flags", "flags": flags, "memo_ids": memo_ids}

    metric_intent = bool(words & METRIC_HINTS) or "over time" in query.lower()
    threads_strong = _strong_matches(query, lookup_threads(conn), "name")
    metrics_strong = _strong_matches(query, lookup_metrics(conn), "series_name")

    # 2. Metric question — only when the query shows quantitative intent.
    if metric_intent and metrics_strong:
        memo_ids = sorted({g for m in metrics_strong for g in _json(m["source_memo_ids"])})
        return {"route": "metrics", "metrics": metrics_strong, "memo_ids": memo_ids}

    # 3. Thread question — a strongly-named issue thread.
    if threads_strong:
        memo_ids = sorted({g for t in threads_strong for g in _json(t["memo_ids"])})
        return {"route": "threads", "threads": threads_strong, "memo_ids": memo_ids}

    # 3b. Metric named strongly without explicit intent still beats keyword search.
    if metrics_strong:
        memo_ids = sorted({g for m in metrics_strong for g in _json(m["source_memo_ids"])})
        return {"route": "metrics", "metrics": metrics_strong, "memo_ids": memo_ids}

    # 4. Default: keyword retrieval + one-hop graph walk -> reasoning.
    seeds = keyword_search(conn, query)
    seed_ids = [m["global_id"] for m in seeds]
    expanded = graph_walk(conn, seed_ids)
    memos = seeds + expanded
    return {
        "route": "reasoning",
        "memos": memos,
        "seed_ids": seed_ids,
        "expanded_ids": [m["global_id"] for m in expanded],
        "memo_ids": [m["global_id"] for m in memos],
    }


def _json(s):
    import json
    try:
        return json.loads(s) if s else []
    except (ValueError, TypeError):
        return []


def _strong_matches(query, items, name_key):
    """
    Filter items (already ranked by name overlap) to those whose name STRONGLY
    matches the query: at least two shared distinctive words, or full coverage
    of a distinctive multi-word name. Prevents a single common word (e.g.
    "parking") from hijacking a direct lookup.
    """
    qwords = set(content_words(query))
    strong = []
    for item in items:
        distinctive = set(content_words(item[name_key])) - GENERIC_NAME_WORDS
        shared = qwords & distinctive
        if len(shared) >= 2 or (len(distinctive) >= 2 and shared == distinctive):
            strong.append(item)
    return strong


# --------------------------------------------------------------------------- #
# Layer 3 — Reasoning
# --------------------------------------------------------------------------- #
SYSTEM_PROMPT = """You are a research analyst for the City of Reno council-memo \
archive. You reason ACROSS memos to surface patterns, tensions, timelines, and \
gaps — you do not summarize individual memos.

Rules you must follow exactly:
- Cite a specific global_id (e.g. JAN-003) as evidence for every claim you make.
- Identify cross-document patterns, contradictions, and timelines. Do not simply \
restate what one memo says.
- Distinguish what the memos SAY (faithful) from what is TRUE in the world. \
Never present a memo's claim as established external fact.
- Use plain language. No jargon, no internal field names.
- Label uncertainty explicitly: say "the memos suggest" rather than "it is the case".
- If the question is fully answerable from a single memo, say so and point to \
that memo rather than manufacturing a cross-document pattern.
- Use only the memos provided in the context block. Do not invent content, \
memo IDs, numbers, or relationships that are not present."""


def build_context_block(memos):
    """Format retrieved memos into a citation-ready context block (bottom-truncated)."""
    memos = memos[:MAX_CONTEXT_MEMOS]
    parts = []
    for m in memos:
        lines = [
            f"[{m['global_id']}] {m.get('title') or '(untitled)'}",
            f"Date: {m.get('date_published') or 'unknown'} | "
            f"Department: {m.get('department') or 'unknown'}",
        ]
        if m.get("tldr"):
            lines.append(f"Summary: {m['tldr']}")
        if m.get("key_stats"):
            lines.append(f"Key stats: {m['key_stats']}")
        if m.get("key_decisions"):
            lines.append(f"Key decisions: {m['key_decisions']}")
        if m.get("action_items"):
            lines.append(f"Action items: {m['action_items']}")
        parts.append("\n".join(lines))
    return "\n\n---\n\n".join(parts)


def reason(query, memos):
    """Call Claude to synthesize across the retrieved memos. Returns the answer text."""
    if not memos:
        return "No memos matched this query, so there is nothing to reason over."

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    context = build_context_block(memos)
    if not api_key:
        cited = ", ".join(m["global_id"] for m in memos[:MAX_CONTEXT_MEMOS])
        return (
            "[Reasoning layer unavailable: ANTHROPIC_API_KEY is not set.]\n\n"
            f"Retrieved and ready for synthesis: {cited}\n\n"
            "Context block prepared below:\n\n" + context
        )

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    user_msg = (
        f"Question: {query}\n\n"
        f"Context block — {min(len(memos), MAX_CONTEXT_MEMOS)} memos:\n\n{context}\n\n"
        "Answer the question by reasoning across these memos. Cite global_ids."
    )
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    return "".join(block.text for block in resp.content if block.type == "text")


# --------------------------------------------------------------------------- #
# Top-level entry point
# --------------------------------------------------------------------------- #
def retrieve(query, db_path=DB_PATH):
    """Run routing + retrieval only (no LLM). Returns the route dict."""
    conn = connect(db_path)
    try:
        return route(conn, query)
    finally:
        conn.close()


def answer(query, db_path=DB_PATH, use_llm=True):
    """
    Full pipeline: route -> retrieve -> (reason if the route needs synthesis).
    Returns a dict with the route, the supporting memo_ids, and a text answer.
    """
    result = retrieve(query, db_path)
    result["query"] = query

    if result["route"] == "reasoning" and use_llm:
        result["answer"] = reason(query, result["memos"])
    elif result["route"] == "reasoning":
        result["answer"] = (
            "Retrieved memos: " + ", ".join(result["memo_ids"]) +
            "  (LLM reasoning disabled)"
        )
    else:
        result["answer"] = _render_direct(result)
    return result


def _render_direct(result):
    """Plain-text rendering of a direct-lookup route (threads/flags/metrics)."""
    import json
    r = result["route"]
    out = []
    if r == "flags":
        for f in result["flags"]:
            src = ", ".join(_json(f["source_memos"])) or f.get("source_raw") or "—"
            out.append(f"{f['priority']}  {f['flag']}\n  Signal: {f['signal']}"
                       f"\n  Status: {f['status']} | Next: {f['next_step']}\n  Sources: {src}")
    elif r == "metrics":
        for m in result["metrics"]:
            periods, values = _json(m["periods"]), _json(m["data_values"])
            series = ", ".join(f"{p}={v}" for p, v in zip(periods, values))
            src = ", ".join(_json(m["source_memo_ids"])) or "—"
            out.append(f"{m['series_name']} ({m['unit']})\n  {m['description'] or ''}"
                       f"\n  {series}\n  Sources: {src}")
    elif r == "threads":
        for t in result["threads"]:
            ids = ", ".join(_json(t["memo_ids"]))
            out.append(f"{t['name']} [{t['status']}]\n  Signal: {t['key_signal']}"
                       f"\n  Memos: {ids}")
    return "\n\n".join(out) if out else "No matching records."


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main():
    args = [a for a in sys.argv[1:] if a != "--no-llm"]
    use_llm = "--no-llm" not in sys.argv
    if not args:
        print('Usage: python query.py [--no-llm] "your question"')
        sys.exit(1)
    query = " ".join(args)
    result = answer(query, use_llm=use_llm)
    print(f"Route: {result['route']}")
    print(f"Sources: {', '.join(result['memo_ids']) or '(none)'}")
    print("-" * 60)
    print(result["answer"])


if __name__ == "__main__":
    main()
