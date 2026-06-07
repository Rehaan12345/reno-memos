"""
vanilla_rag.py — the baseline (un-grounded) RAG for A-vanilla and B-vanilla.

Truly standard, industry-default RAG with NO research-derived design:
  flatten documents -> fixed-size token chunking -> off-the-shelf embeddings
  -> top-k cosine retrieval -> stuff into a generic prompt -> generate.

No entity normalization, no relationship graph, no bounded vocab, no
thread/flag awareness, no citation requirement, no structured reasoning prompt,
no reranking. This is the control group; it is deliberately not improved.

Every tunable (chunk_size, overlap, top_k, embedding model, the generic prompt,
the generation model/params) is read from eval/systems.config.json via contract.
Nothing here is hardcoded. The only system-specific logic is which raw documents
feed the pipeline (spreadsheet rows for A-vanilla; raw PDF text for B-vanilla).

CLI:
    python eval/vanilla_rag.py --build A-vanilla
    python eval/vanilla_rag.py A-vanilla "your question"
"""

import pickle
import sys

import numpy as np

import contract

try:
    from dotenv import load_dotenv

    load_dotenv(contract.ROOT / ".env")
except ImportError:
    pass

INDEX_DIR = contract.EVAL_DIR / "index"

_model_cache = {}


def _embedder(name):
    from sentence_transformers import SentenceTransformer

    if name not in _model_cache:
        _model_cache[name] = SentenceTransformer(name)
    return _model_cache[name]


# --------------------------------------------------------------------------- #
# Documents — the raw text each vanilla system ingests
# --------------------------------------------------------------------------- #
def load_documents(system_id):
    """Return [{'id', 'text', 'title', 'source_url'}] for a vanilla system."""
    sysc = contract.get_system(system_id)
    src = sysc["data_source"]
    if src == "spreadsheet":
        return _spreadsheet_documents(contract.ROOT / sysc["spreadsheet_path"])
    if src == "pdf_urls":
        return _pdf_documents()
    raise ValueError(f"unknown data_source '{src}' for {system_id}")


def _spreadsheet_documents(path):
    """
    Flatten each memo row of the raw Master Log to a text blob. Vanilla touches
    ONLY the memo rows — it gets no curated threads/flags/decisions/metrics
    structure (no thread/flag awareness, per the baseline spec).
    """
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["01 · Master Log"]
    rows = list(ws.iter_rows(values_only=True))
    headers = [str(h).strip() if h is not None else "" for h in rows[0]]
    title_i = headers.index("Title") if "Title" in headers else None
    url_i = headers.index("Source URL") if "Source URL" in headers else None

    docs = []
    for r in rows[1:]:
        if not r or all(c is None for c in r):
            continue
        gid = str(r[0]).strip() if r[0] is not None else None
        if not gid:
            continue
        lines = []
        for h, c in zip(headers, r):
            if c is None:
                continue
            val = str(c).strip()
            if not val or val.lower() == "none":
                continue
            lines.append(f"{h}: {val}")
        docs.append({
            "id": gid,
            "text": "\n".join(lines),
            "title": str(r[title_i]).strip() if title_i is not None and r[title_i] else None,
            "source_url": str(r[url_i]).strip() if url_i is not None and r[url_i] else None,
        })
    return docs


def _pdf_documents():
    """
    B-vanilla document source — the resolved Experiment B PDF set. Reads the raw
    extracted PDF text (no structured fields); vanilla sees only memo text.
    """
    import json

    manifest_path = contract.EVAL_DIR / "experiment_b" / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            "Experiment B manifest missing. Run experiment_b_ingest.py first."
        )
    manifest = json.loads(manifest_path.read_text())
    docs = []
    for d in manifest["documents"]:
        text = (contract.EVAL_DIR / "experiment_b" / d["text_path"]).read_text(encoding="utf-8")
        docs.append({
            "id": d["doc_id"],
            "text": text,
            "title": d["title"],
            "source_url": d["source_url"],
        })
    return docs


# --------------------------------------------------------------------------- #
# Fixed-size token chunking
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# Index build / load
# --------------------------------------------------------------------------- #
def build_index(system_id, rebuild=False):
    path = INDEX_DIR / f"{system_id}.pkl"
    if path.exists() and not rebuild:
        return path
    sysc = contract.get_system(system_id)
    model = _embedder(sysc["embedding_model"])
    docs = load_documents(system_id)

    chunks, chunk_ids = [], []
    for d in docs:
        for i, ch in enumerate(_chunk(d["text"], model.tokenizer,
                                      int(sysc["chunk_size"]), int(sysc["overlap"]))):
            chunks.append(ch)
            chunk_ids.append(f"{d['id']}#{i}")

    embeddings = model.encode(chunks, normalize_embeddings=True, convert_to_numpy=True)
    INDEX_DIR.mkdir(exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump({
            "chunks": chunks,
            "chunk_ids": chunk_ids,
            "embeddings": embeddings,
            "embedding_model": sysc["embedding_model"],
            "chunk_size": sysc["chunk_size"],
            "overlap": sysc["overlap"],
            "n_docs": len(docs),
        }, f)
    return path


def _load_index(system_id):
    path = INDEX_DIR / f"{system_id}.pkl"
    if not path.exists():
        build_index(system_id)
    with open(path, "rb") as f:
        return pickle.load(f)


# --------------------------------------------------------------------------- #
# Generation
# --------------------------------------------------------------------------- #
def _generate(prompt):
    from generate import generate

    return generate(prompt)  # vanilla: generic prompt only, no system prompt


# --------------------------------------------------------------------------- #
# Query
# --------------------------------------------------------------------------- #
def query(system_id, question):
    """
    Run the vanilla pipeline for one question. Returns the run-record `output`
    shape: prose answer, empty cited_sources (vanilla does not cite), and the
    internal retrieved_chunk_ids (for miss-detection only, never shown).
    """
    sysc = contract.get_system(system_id)
    idx = _load_index(system_id)
    model = _embedder(sysc["embedding_model"])

    qv = model.encode([question], normalize_embeddings=True, convert_to_numpy=True)[0]
    sims = idx["embeddings"] @ qv
    k = int(sysc["top_k"])
    top = np.argsort(-sims)[:k]

    context = "\n\n---\n\n".join(idx["chunks"][i] for i in top)
    prompt = sysc["generic_prompt"].format(context=context, question=question)
    answer = _generate(prompt)

    return {
        "answer": answer,
        "cited_sources": [],
        "extracted_data": None,
        "retrieved_chunk_ids": [idx["chunk_ids"][i] for i in top],
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main():
    args = sys.argv[1:]
    if args and args[0] == "--build":
        path = build_index(args[1], rebuild=True)
        idx = _load_index(args[1])
        print(f"Built {path.name}: {len(idx['chunks'])} chunks "
              f"from {idx['n_docs']} docs, model={idx['embedding_model']}")
        return
    if len(args) < 2:
        print('Usage: python eval/vanilla_rag.py [--build] <system_id> "question"')
        sys.exit(1)
    system_id, question = args[0], " ".join(args[1:])
    r = query(system_id, question)
    print(f"Retrieved chunks (internal): {r['retrieved_chunk_ids']}")
    print("-" * 60)
    print(r["answer"])


if __name__ == "__main__":
    main()
