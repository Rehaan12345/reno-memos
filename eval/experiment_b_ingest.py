"""
experiment_b_ingest.py — Experiment B document-resolution API.

Resolves the raw council-memo PDF set from the live Reno site, applies the
year + date-ceiling filters from the contract, fetches and extracts the
qualifying PDFs, and writes an auditable log so the cutoff can be eyeballed
before any system runs.

Both B systems (B-research, B-vanilla) consume the SAME resolved set written
here. The document_set_hash is computed over the fetched PDF bytes; equal hash
across both systems is the precondition for a valid B comparison.

Findings about the site (verified 2026-06):
  - The page is behind Akamai bot protection: a bare request 403s. The memo
    list is NOT JS-injected — once the full browser header set is sent
    (sec-fetch-*, sec-ch-ua), the server returns the list in the HTML.
  - The memos live in a tabbed widget with year tabs (2026 / 2025 / 2024).
    Each <li> is "Month D, YYYY -&nbsp;<a href=...showpublisheddocument/ID/..>
    Title</a>" — the publication date is explicit, not inferred.

Run:
    python eval/experiment_b_ingest.py            # resolve + fetch + log
    python eval/experiment_b_ingest.py --dry-run  # resolve + classify only, no PDF fetch
"""

import hashlib
import html
import json
import re
import sys
import urllib.request
from datetime import date

import contract

OUT_DIR = contract.EVAL_DIR / "experiment_b"
DOCS_DIR = OUT_DIR / "documents"
HOST = "https://www.reno.gov"

# Full browser header set — Akamai 403s without the sec-fetch-* / sec-ch-ua set.
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
              "image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Upgrade-Insecure-Requests": "1",
}

_MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], 1)}


# --------------------------------------------------------------------------- #
# Fetch
# --------------------------------------------------------------------------- #
def _fetch(url, binary=False):
    req = urllib.request.Request(url, headers=BROWSER_HEADERS)
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    return data if binary else data.decode("utf-8", errors="replace")


def _strip_tags(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s)).replace("\xa0", " ").strip()


def _parse_date(text):
    m = re.match(r"([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})", text.strip())
    if not m or m.group(1) not in _MONTHS:
        return None
    return date(int(m.group(3)), _MONTHS[m.group(1)], int(m.group(2)))


# --------------------------------------------------------------------------- #
# Resolve the listing
# --------------------------------------------------------------------------- #
def resolve_listing(page_html):
    """
    Parse the memos widget's year tabs into a flat list of found memos:
      {doc_id, year, publication_date (ISO|None), title, source_url}
    Returns every memo across every year tab (so wrong-year exclusions are logged).
    """
    # Map each year-tab panel id to its year label.
    labels = dict(re.findall(r'href="#(679_5504_5422\d)">(\d{4})</a>', page_html))

    def panel(pid):
        m = re.search(
            r"<div id='%s'[^>]*tab_section[^>]*>(.*?)</div>\s*"
            r"(?=<div id='679_5504_5422\d'|</div>)" % pid, page_html, re.S)
        return m.group(1) if m else ""

    found = []
    for pid, year in labels.items():
        for li in re.findall(r"<li>(.*?)</li>", panel(pid), re.S):
            a = re.search(
                r'<a href="([^"]*showpublisheddocument/(\d+)[^"]*)"[^>]*>(.*?)</a>',
                li, re.S)
            if not a:
                continue
            url, doc_id, title_html = a.group(1), a.group(2), a.group(3)
            d = _parse_date(_strip_tags(li[:a.start()]).strip(" -–"))
            found.append({
                "doc_id": doc_id,
                "year": int(year),
                "publication_date": d.isoformat() if d else None,
                "title": _strip_tags(title_html),
                "source_url": url if url.startswith("http") else HOST + url,
            })
    return found


def _spreadsheet_docset():
    """The doc ids the spreadsheet's curators included (from reno.db source_url)."""
    import sqlite3

    con = sqlite3.connect(contract.ROOT / "reno.db")
    try:
        urls = [r[0] for r in con.execute("SELECT source_url FROM memos") if r[0]]
    finally:
        con.close()
    ids = set()
    for u in urls:
        m = re.search(r"showpublisheddocument/(\d+)", u)
        if m:
            ids.add(m.group(1))
    return ids


def classify(found):
    """
    Apply the contract's year + date-ceiling filters, then (if enabled) restrict
    to the spreadsheet's curated doc set. Annotates each memo with `included`
    (bool) and `exclusion_reason` (or None) from the contract's vocabulary.
    """
    cfg = contract.load_config()["experiment_B_ingestion"]
    year_filter = cfg["filters"]["year"]
    ceiling = date.fromisoformat(cfg["filters"]["date_ceiling_inclusive"])
    restrict = cfg["filters"].get("restrict_to_spreadsheet_docset", False)
    ss_ids = _spreadsheet_docset() if restrict else None
    for m in found:
        if m["year"] != year_filter:
            m["included"], m["exclusion_reason"] = False, "wrong_year"
        elif m["publication_date"] is None:
            m["included"], m["exclusion_reason"] = False, "fetch_failed"  # unparseable date
        elif date.fromisoformat(m["publication_date"]) > ceiling:
            m["included"], m["exclusion_reason"] = False, "after_cutoff"
        elif restrict and m["doc_id"] not in ss_ids:
            m["included"], m["exclusion_reason"] = False, "not_in_spreadsheet"
        else:
            m["included"], m["exclusion_reason"] = True, None
    return found, ceiling


# --------------------------------------------------------------------------- #
# Fetch + extract included PDFs
# --------------------------------------------------------------------------- #
def _extract_pdf_text(pdf_bytes):
    import io
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def fetch_included(memos):
    """Fetch + extract each included memo. Marks fetch_failed on error. In place."""
    import shutil

    # Rebuild the docs dir from scratch so it holds exactly the current set.
    if DOCS_DIR.exists():
        shutil.rmtree(DOCS_DIR)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    for m in memos:
        if not m["included"]:
            continue
        try:
            pdf = _fetch(m["source_url"], binary=True)
            text = _extract_pdf_text(pdf)
            m["pdf_sha256"] = hashlib.sha256(pdf).hexdigest()
            m["pdf_bytes"] = len(pdf)
            m["char_count"] = len(text)
            (DOCS_DIR / f"{m['doc_id']}.txt").write_text(text, encoding="utf-8")
            m["text_path"] = f"documents/{m['doc_id']}.txt"
        except Exception as e:  # a failed fetch is recorded, never silently dropped
            m["included"] = False
            m["exclusion_reason"] = "fetch_failed"
            m["fetch_error"] = f"{type(e).__name__}: {e}"
    return memos


def _document_set_hash(memos):
    parts = [f"{m['doc_id']}:{m['pdf_sha256']}"
             for m in sorted(memos, key=lambda x: x["doc_id"])
             if m["included"]]
    return "sha256:" + hashlib.sha256("\n".join(parts).encode()).hexdigest()


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def run(dry_run=False):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cfg = contract.load_config()["experiment_B_ingestion"]

    page = _fetch(cfg["source_page"])
    (OUT_DIR / "listing.html").write_text(page, encoding="utf-8")

    found = resolve_listing(page)
    found, ceiling = classify(found)

    if not dry_run:
        fetch_included(found)

    included = [m for m in found if m["included"]]
    doc_hash = _document_set_hash(included) if (included and not dry_run) else None

    # Cross-check against the spreadsheet (Experiment A) reference count.
    expected = cfg["expected_count_reference"]

    log = {
        "source_page": cfg["source_page"],
        "year_filter": cfg["filters"]["year"],
        "date_ceiling_inclusive": cfg["filters"]["date_ceiling_inclusive"],
        "resolved_at_local_date": date.today().isoformat(),
        "counts": {
            "found_total": len(found),
            "included": len(included),
            "excluded_wrong_year": sum(1 for m in found if m["exclusion_reason"] == "wrong_year"),
            "excluded_after_cutoff": sum(1 for m in found if m["exclusion_reason"] == "after_cutoff"),
            "excluded_fetch_failed": sum(1 for m in found if m["exclusion_reason"] == "fetch_failed"),
        },
        "spreadsheet_expected_count_reference": expected,
        "document_set_hash": doc_hash,
        "memos": found,
    }
    (OUT_DIR / "ingestion_log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
    if not dry_run:
        manifest = {
            "document_set_hash": doc_hash,
            "date_ceiling_inclusive": cfg["filters"]["date_ceiling_inclusive"],
            "documents": [
                {k: m[k] for k in ("doc_id", "title", "publication_date",
                                   "source_url", "text_path", "pdf_sha256")}
                for m in included
            ],
        }
        (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return log


def _print_summary(log):
    c = log["counts"]
    print(f"Source: {log['source_page']}")
    print(f"Year filter: {log['year_filter']} | Ceiling (inclusive): {log['date_ceiling_inclusive']}")
    print("-" * 64)
    print(f"  Found (all year tabs)     : {c['found_total']}")
    print(f"  EXCLUDED wrong_year       : {c['excluded_wrong_year']}")
    print(f"  EXCLUDED after_cutoff     : {c['excluded_after_cutoff']}")
    print(f"  EXCLUDED fetch_failed     : {c['excluded_fetch_failed']}")
    print(f"  INCLUDED (fetched ok)     : {c['included']}")
    print("-" * 64)
    print(f"  Spreadsheet reference     : {log['spreadsheet_expected_count_reference']}")
    print(f"  document_set_hash         : {log['document_set_hash']}")
    inc = sorted([m for m in log["memos"] if m["included"]], key=lambda x: x["publication_date"])
    if inc:
        print(f"  Included date range       : {inc[0]['publication_date']} -> {inc[-1]['publication_date']}")
    print(f"\nFull per-memo log: {(OUT_DIR / 'ingestion_log.json')}")


def main():
    dry = "--dry-run" in sys.argv
    log = run(dry_run=dry)
    _print_summary(log)


if __name__ == "__main__":
    main()
