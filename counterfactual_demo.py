"""
counterfactual_demo.py — throwaway demonstration (safe to delete).

Runs ONE question through three conditions to show how the research-grounded
design decisions change the output:

  A. Full system        : keyword seeds + one-hop graph walk + structured prompt
  B. Graph walk OFF     : keyword seeds only      + structured prompt
                          (isolates DocRED + Meng — the connections that only
                           exist via the relationship graph)
  C. Unstructured prompt: full retrieval + a generic "answer this" prompt
                          (isolates CORE-KG — synthesis vs. summary, and the
                           citation/faithfulness discipline)

Reuses query.py's engine; does not modify it. Needs ANTHROPIC_API_KEY
(loaded from .env by importing query).
"""

import re
import anthropic

import query

Q = "How are DMV holds affecting parking revenue and downtown enforcement?"
GID = re.compile(r"\b[A-Z]{3}-\d{3}\b")


def cited_ids(text):
    return sorted(set(GID.findall(text)))


def call(system, memos, user_prefix):
    ctx = query.build_context_block(memos)
    user = f"{user_prefix}Question: {Q}\n\nContext:\n\n{ctx}"
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=query.MODEL,
        max_tokens=900,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(b.text for b in resp.content if b.type == "text")


def show(label, answer):
    ids = cited_ids(answer)
    print(f"\n{'=' * 70}\n{label}\n{'=' * 70}")
    print(f"length: {len(answer)} chars | distinct memo_ids cited: {len(ids)} -> {ids}")
    print("-" * 70)
    print(answer.strip()[:1100])


# ---- Retrieval (same mechanics query.py uses for the reasoning route) ----
conn = query.connect()
seeds = query.keyword_search(conn, Q)
seed_ids = [m["global_id"] for m in seeds]
expanded = query.graph_walk(conn, seed_ids)
expanded_ids = [m["global_id"] for m in expanded]
conn.close()
full = seeds + expanded

print(f"QUESTION: {Q}\n")
print(f"Keyword seeds ({len(seed_ids)}):        {seed_ids}")
print(f"Added by one-hop graph walk ({len(expanded_ids)}): {expanded_ids}")
print(f"Full retrieved set passed to A & C: {len(full)} memos")

STRUCTURED_PREFIX = "Answer by reasoning across these memos. Cite global_ids.\n\n"
GENERIC_PROMPT = (
    "You are a helpful assistant. Answer the user's question using the "
    "documents provided below."
)

a = call(query.SYSTEM_PROMPT, full, STRUCTURED_PREFIX)
b = call(query.SYSTEM_PROMPT, seeds, STRUCTURED_PREFIX)
c = call(GENERIC_PROMPT, full, "")

show("A. FULL SYSTEM  (graph walk ON, structured prompt)", a)
show("B. GRAPH WALK OFF  (keyword seeds only, structured prompt)", b)
show("C. UNSTRUCTURED PROMPT  (full retrieval, generic prompt)", c)
