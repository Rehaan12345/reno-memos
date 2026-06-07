"""
experiment_b_research.py — B-research: the full ARCHITECTURE.md / CLAUDE.md
extraction pipeline run on the raw Experiment B PDFs.

Unlike A-research (which inherits the human-curated spreadsheet), B-research
BUILDS its own structured knowledge base from raw PDF text, following the
research methodology:

  1. Assign canonical global_ids (MON-### by date) to the resolved doc set.
  2. Coreference resolution  — a SEPARATE pass, before extraction (CLAUDE.md).
  3. Sequential typed extraction on the resolved text — entity types in the
     prescribed order (departments -> projects -> dollars -> dates -> people),
     plus structured fields (tldr, key_stats, key_decisions, action_items).
  4. Entity normalization — a canonicalization pass building an entity registry
     so surface-form variants collapse to one canonical name (mandatory; the
     primary defense against false-negative relations).
  5. Bounded-vocabulary relation extraction over the normalized entities — only
     the approved relation types, evidence-grounded, never free-form.
  6. Build reno_b.db (memos + relationships + entities + FTS) and retrieve /
     reason over it, reusing the SAME research retrieval + reasoning layer as
     A-research (query.py), so the only B-pair variable is the grounding.

Per-memo extraction is cached under experiment_b/extracted/ so re-runs are cheap
and the expensive LLM passes run once.

CLI:
    python eval/experiment_b_research.py --build          # run/refresh the pipeline
    python eval/experiment_b_research.py "your question"  # query the built KB
"""

import json
import re
import sqlite3
import sys
from datetime import date
from itertools import combinations

import contract

sys.path.insert(0, str(contract.ROOT))  # so we can reuse the A-research engine
import query  # noqa: E402  (keyword_search, graph_walk, build_context_block, SYSTEM_PROMPT)
from generate import generate  # noqa: E402

B_DIR = contract.EVAL_DIR / "experiment_b"
EXTRACT_DIR = B_DIR / "extracted"
B_DB = B_DIR / "reno_b.db"

MONTH_ABBR = ["", "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
              "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

# Bounded relation vocabulary — from CLAUDE.md. The LLM may NOT invent others.
APPROVED_RELATIONS = [
    "funds", "authorizes", "depends_on", "same_project",
    "references", "precedes", "assigned_to", "conflicts_with",
]

# Seed canonical department forms from CLAUDE.md's normalization examples.
REGISTRY_SEED = {
    "departments": ["Public Works", "City Manager's Office", "City Council"],
}

# --------------------------------------------------------------------------- #
# Prompts (research grounding — not eval-contract tunables)
# --------------------------------------------------------------------------- #
COREF_SYSTEM = (
    "You resolve coreferences in a City of Reno council memo. Rewrite the memo "
    "text so every pronoun and vague reference is replaced by the specific "
    "entity it refers to (e.g. 'the department' -> the actual department name, "
    "'it' -> the named project). Change nothing else: keep all facts, numbers, "
    "dates, and names exactly. Output only the resolved text, no commentary."
)

EXTRACT_SYSTEM = (
    "You extract structured data from a coreference-resolved City of Reno "
    "council memo. Work through the entity types IN THIS ORDER, one at a time, "
    "to avoid attention drift: (1) departments/offices, (2) named projects and "
    "programs, (3) dollar amounts and budget items, (4) dates and deadlines, "
    "(5) named individuals and roles. Then extract the summary fields.\n\n"
    "Return ONLY a JSON object with exactly these keys:\n"
    '{"department": str|null, "authors": str|null, "category": str|null, '
    '"subcategory": str|null, "tldr": str (2-4 plain-language sentences), '
    '"key_stats": str|null, "key_decisions": str|null, "action_items": str|null, '
    '"keywords": [str], "entities": {"departments": [str], "projects": [str], '
    '"dollar_amounts": [str], "dates": [str], "people": [str]}}\n'
    "Use null for absent fields. Never invent content not in the memo."
)

NORMALIZE_SYSTEM = (
    "You canonicalize entity names for a City of Reno knowledge graph. Given a "
    "list of surface forms, identify the groups that refer to the SAME real "
    "entity and assign each group ONE canonical name (e.g. 'PW', 'Public Works "
    "Dept', 'the department' -> 'Public Works'). Return ONLY a JSON object "
    "mapping each canonical name to the list of surface-form variants that "
    'collapse to it: {"Public Works": ["PW", "Public Works Dept"], ...}. '
    "Include ONLY entities that actually have variants to merge or whose surface "
    "form should be cleaned up; omit forms that are already canonical and "
    "standalone. Never merge genuinely distinct entities."
)

RELATION_SYSTEM = (
    "You decide whether a directed relation holds between two City of Reno "
    "memos, A and B, using ONLY this bounded vocabulary: "
    + ", ".join(APPROVED_RELATIONS) + ". "
    "Definitions: funds = A allocates budget to B's item; authorizes = A grants "
    "approval for B's action; depends_on = A's action requires B's completion; "
    "same_project = A and B concern the same named project; references = A "
    "explicitly cites B; precedes = A's decision temporally/logically precedes "
    "B; assigned_to = A's action is owned by an entity in B; conflicts_with = "
    "A's recommendation contradicts B's. Return ONLY JSON: "
    '{"relation": one of the vocabulary or "none", "evidence": str}. '
    "Choose 'none' unless the memo text clearly supports a relation. Never "
    "invent a relation type outside the vocabulary."
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _parse_json(text):
    """Parse a JSON object from a model response, tolerating code fences."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0) if m else text)


def _load_manifest():
    manifest = json.loads((B_DIR / "manifest.json").read_text())
    docs = []
    for d in manifest["documents"]:
        docs.append({
            **d,
            "raw_text": (B_DIR / d["text_path"]).read_text(encoding="utf-8"),
            "pub_date": date.fromisoformat(d["publication_date"]),
        })
    return manifest["document_set_hash"], docs


def assign_global_ids(docs):
    """MON-### per month, ordered by (date, doc_id) — B's own canonical ids."""
    docs = sorted(docs, key=lambda d: (d["pub_date"], d["doc_id"]))
    counters = {}
    for d in docs:
        mon = MONTH_ABBR[d["pub_date"].month]
        counters[mon] = counters.get(mon, 0) + 1
        d["global_id"] = f"{mon}-{counters[mon]:03d}"
        d["month"] = mon
        d["memo_id"] = counters[mon]
    return docs


# --------------------------------------------------------------------------- #
# Per-memo extraction (cached)
# --------------------------------------------------------------------------- #
def extract_memo(doc, rebuild=False):
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    cache = EXTRACT_DIR / f"{doc['global_id']}.json"
    if cache.exists() and not rebuild:
        return json.loads(cache.read_text())

    # Pass 1 — coreference resolution (separate pass, before extraction).
    resolved = generate(doc["raw_text"][:24000], system=COREF_SYSTEM, max_tokens=8192)
    # Pass 2 — sequential typed extraction + fields on the resolved text.
    fields = _parse_json(generate(resolved[:18000], system=EXTRACT_SYSTEM, max_tokens=4096))

    rec = {
        "global_id": doc["global_id"], "month": doc["month"], "memo_id": doc["memo_id"],
        "date_published": doc["publication_date"], "title": doc["title"],
        "source_url": doc["source_url"], "doc_id": doc["doc_id"],
        "resolved_text": resolved, "fields": fields,
    }
    cache.write_text(json.dumps(rec, indent=2))
    return rec


# --------------------------------------------------------------------------- #
# Entity normalization (canonicalization pass -> registry)
# --------------------------------------------------------------------------- #
def normalize_entities(records, rebuild=False):
    reg_path = B_DIR / "entity_registry.json"
    if reg_path.exists() and not rebuild:
        registry = json.loads(reg_path.read_text())
    else:
        registry = {}
        for etype in ("departments", "projects", "people"):
            surfaces = sorted({s for r in records for s in r["fields"]["entities"].get(etype, []) if s})
            seed = REGISTRY_SEED.get(etype, [])
            surf2canon = {}
            if surfaces:
                payload = json.dumps({"surface_forms": surfaces, "known_canonical": seed})
                try:
                    clusters = _parse_json(generate(payload, system=NORMALIZE_SYSTEM, max_tokens=8192))
                    for canonical, variants in clusters.items():
                        surf2canon[canonical] = canonical
                        for v in variants:
                            surf2canon[v] = canonical
                except Exception as e:  # never crash the build on a normalization hiccup
                    print(f"  [warn] normalization parse failed for {etype} ({e}); using identity map")
            registry[etype] = surf2canon  # unlisted forms map to themselves at apply time
        reg_path.write_text(json.dumps(registry, indent=2))

    # Apply the registry to each record -> canonical entity sets.
    for r in records:
        canon = {}
        for etype in ("departments", "projects", "people"):
            mp = registry.get(etype, {})
            canon[etype] = sorted({mp.get(s, s) for s in r["fields"]["entities"].get(etype, []) if s})
        canon["dollar_amounts"] = r["fields"]["entities"].get("dollar_amounts", [])
        canon["dates"] = r["fields"]["entities"].get("dates", [])
        r["canonical_entities"] = canon
    return records, registry


# --------------------------------------------------------------------------- #
# Bounded-vocabulary relation extraction
# --------------------------------------------------------------------------- #
def extract_relations(records, rebuild=False):
    rel_path = B_DIR / "relationships.json"
    if rel_path.exists() and not rebuild:
        return json.loads(rel_path.read_text())

    by_id = {r["global_id"]: r for r in records}
    # Candidate pairs share at least one canonical project (distinctive entity).
    pairs = []
    for a, b in combinations(sorted(by_id), 2):
        shared = set(by_id[a]["canonical_entities"]["projects"]) & set(by_id[b]["canonical_entities"]["projects"])
        if shared:
            pairs.append((a, b, sorted(shared)))

    edges = []
    for a, b, shared in pairs:
        # Order source->target by date so 'precedes' is meaningful.
        s, t = sorted([a, b], key=lambda g: by_id[g]["date_published"])
        edges.append({"source_id": s, "target_id": t, "rel_type": "same_project",
                      "evidence": f"Shared project(s): {', '.join(shared)}"})
        # Ask whether a stronger directed relation also holds (bounded vocab).
        def brief(g):
            r = by_id[g]
            return (f"{g} ({r['date_published']}) {r['title']}\n"
                    f"TLDR: {r['fields'].get('tldr')}\n"
                    f"Decisions: {r['fields'].get('key_decisions')}\n"
                    f"Actions: {r['fields'].get('action_items')}")
        msg = f"Memo A:\n{brief(s)}\n\nMemo B:\n{brief(t)}"
        try:
            res = _parse_json(generate(msg, system=RELATION_SYSTEM))
            rel = res.get("relation")
            if rel in APPROVED_RELATIONS and rel != "same_project":
                edges.append({"source_id": s, "target_id": t, "rel_type": rel,
                              "evidence": (res.get("evidence") or "")[:300]})
        except Exception:
            pass  # a missed relation is acceptable; a hallucinated one is not

    rel_path.write_text(json.dumps(edges, indent=2))
    return edges


# --------------------------------------------------------------------------- #
# Build reno_b.db (schema-compatible with query.py)
# --------------------------------------------------------------------------- #
def build_db(records, edges):
    if B_DB.exists():
        B_DB.unlink()
    conn = sqlite3.connect(B_DB)
    conn.executescript("""
        CREATE TABLE memos (
            global_id TEXT PRIMARY KEY, month TEXT, memo_id INTEGER,
            date_published TEXT, title TEXT, department TEXT, authors TEXT,
            category TEXT, subcategory TEXT, tldr TEXT, key_stats TEXT,
            key_decisions TEXT, action_items TEXT, keywords TEXT,
            source_url TEXT, search_text TEXT
        );
        CREATE TABLE relationships (
            source_id TEXT, target_id TEXT, rel_type TEXT, evidence TEXT
        );
        CREATE TABLE entities (
            name TEXT, etype TEXT, memo_ids TEXT
        );
        CREATE VIRTUAL TABLE memos_fts USING fts5(global_id UNINDEXED, search_text);
    """)
    ent_index = {}
    for r in records:
        f = r["fields"]
        ents = r["canonical_entities"]
        keywords = ", ".join(f.get("keywords") or [])
        searchable = [r["title"], f.get("department"), f.get("category"),
                      f.get("subcategory"), f.get("tldr"), f.get("key_stats"),
                      f.get("key_decisions"), f.get("action_items"), keywords,
                      ", ".join(ents["departments"] + ents["projects"] + ents["people"])]
        search_text = " ".join(x for x in searchable if x)
        conn.execute(
            "INSERT INTO memos VALUES (:global_id,:month,:memo_id,:date_published,"
            ":title,:department,:authors,:category,:subcategory,:tldr,:key_stats,"
            ":key_decisions,:action_items,:keywords,:source_url,:search_text)",
            {"global_id": r["global_id"], "month": r["month"], "memo_id": r["memo_id"],
             "date_published": r["date_published"], "title": r["title"],
             "department": f.get("department"), "authors": f.get("authors"),
             "category": f.get("category"), "subcategory": f.get("subcategory"),
             "tldr": f.get("tldr"), "key_stats": f.get("key_stats"),
             "key_decisions": f.get("key_decisions"), "action_items": f.get("action_items"),
             "keywords": keywords, "source_url": r["source_url"], "search_text": search_text})
        for etype in ("departments", "projects", "people"):
            for name in ents[etype]:
                ent_index.setdefault((name, etype), []).append(r["global_id"])
    for e in edges:
        conn.execute("INSERT INTO relationships VALUES (?,?,?,?)",
                     (e["source_id"], e["target_id"], e["rel_type"], e.get("evidence")))
    for (name, etype), ids in ent_index.items():
        conn.execute("INSERT INTO entities VALUES (?,?,?)", (name, etype, json.dumps(sorted(set(ids)))))
    conn.execute("INSERT INTO memos_fts (global_id, search_text) SELECT global_id, search_text FROM memos")
    conn.commit()
    conn.close()


def build(rebuild=False):
    """Run the full extraction pipeline and (re)build reno_b.db."""
    doc_hash, docs = _load_manifest()
    docs = assign_global_ids(docs)
    print(f"document_set_hash: {doc_hash}")
    records = []
    for i, d in enumerate(docs, 1):
        rec = extract_memo(d, rebuild=rebuild)
        rec["canonical_entities"] = {}  # filled by normalize
        records.append(rec)
        print(f"  extracted {i}/{len(docs)}  {rec['global_id']}  {rec['title'][:50]}")
    records, registry = normalize_entities(records, rebuild=rebuild)
    print(f"entity registry: " + ", ".join(f"{k}={len(v)}" for k, v in registry.items()))
    edges = extract_relations(records, rebuild=rebuild)
    print(f"relationships extracted: {len(edges)}")
    build_db(records, edges)
    print(f"built {B_DB.name}: {len(records)} memos, {len(edges)} edges")
    return doc_hash


# --------------------------------------------------------------------------- #
# Retrieval + reasoning (reuses the A-research engine over reno_b.db)
# --------------------------------------------------------------------------- #
def _connect():
    conn = sqlite3.connect(B_DB)
    conn.row_factory = sqlite3.Row
    return conn


def query_b(question):
    """Research retrieval + reasoning over the self-built KB. Returns run output."""
    conn = _connect()
    try:
        seeds = query.keyword_search(conn, question)
        seed_ids = [m["global_id"] for m in seeds]
        expanded = query.graph_walk(conn, seed_ids)
        memos = (seeds + expanded)[:query.MAX_CONTEXT_MEMOS]
        context = query.build_context_block(memos)
        user_msg = (
            f"Question: {question}\n\n"
            f"Context block — {len(memos)} memos:\n\n{context}\n\n"
            "Answer the question by reasoning across these memos. Cite global_ids."
        )
        answer = generate(user_msg, system=query.SYSTEM_PROMPT) if memos else \
            "No memos matched this query, so there is nothing to reason over."

        used_ids = [m["global_id"] for m in memos]
        rels = [dict(r) for r in conn.execute(
            "SELECT source_id, target_id, rel_type, evidence FROM relationships "
            "WHERE source_id IN (%s) OR target_id IN (%s)" %
            (",".join("?" * len(used_ids)), ",".join("?" * len(used_ids))),
            used_ids + used_ids).fetchall()] if used_ids else []
        ent_rows = conn.execute(
            "SELECT name, etype, memo_ids FROM entities").fetchall() if used_ids else []
        entities = [{"name": r["name"], "type": r["etype"],
                     "memo_ids": [g for g in json.loads(r["memo_ids"]) if g in used_ids]}
                    for r in ent_rows]
        entities = [e for e in entities if e["memo_ids"]]
        fields = {m["global_id"]: {k: m[k] for k in
                  ("title", "department", "category", "tldr", "key_stats",
                   "key_decisions", "action_items")} for m in memos}

        return {
            "answer": answer,
            "cited_sources": [{"memo_id": m["global_id"], "title": m["title"],
                               "source_url": m["source_url"]} for m in memos],
            "extracted_data": {"entities": entities, "relationships": rels, "fields": fields},
            "retrieved_chunk_ids": used_ids,
        }
    finally:
        conn.close()


def main():
    args = sys.argv[1:]
    if args and args[0] == "--build":
        build(rebuild="--rebuild" in args)
        return
    if not args:
        print('Usage: python eval/experiment_b_research.py [--build] "question"')
        sys.exit(1)
    r = query_b(" ".join(args))
    print("Cited:", [c["memo_id"] for c in r["cited_sources"]])
    print("-" * 60)
    print(r["answer"])


if __name__ == "__main__":
    main()
