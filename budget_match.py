"""Match legislative agenda bills against a Massachusetts budget, section by section.

Examples (from the repository root):
  python budget_match.py --no-embed --limit 3
  python budget_match.py                          # full, uses embeddings
  python budget_match.py --budget FY27_final_budget_text.txt
  python budget_match.py --budget enacted_budget.pdf --no-embed
  python budget_match.py --bills output/all_bills.jsonl --no-embed

Outputs: output/budget_scores.csv and output/budget_sections.csv
"""

import argparse
import io
import json
import re
from pathlib import Path

import pandas as pd

from merge_match import (
    Embedder, SECTION_RE, SUBSECTION_RE, _chunk, _split_on, norm_bill_id,
)
from budget_match_core import match_budget_pair, prepare_budget_target

DEFAULT_BUDGET_URL = "https://malegislature.gov/Bills/194/H5555.pdf"
LINE_ITEM_START_RE = re.compile(r"(?m)^[ \t]*(\d{4}-\d{4})[ \t]+")


def split_budget_sections(text, max_words=300, chunk_words=200):
    """Split budget into named SECTIONs and appropriation line items.

    Preserve budget line-item IDs in labels where a line starts with one;
    otherwise fall back to the same Section / word chunking as merge_match.py.
    """
    units = []
    for sec_label, sec_text in _split_on(SECTION_RE, str(text or ""), ""):
        for label, body in _split_on(LINE_ITEM_START_RE, sec_text, sec_label):
            pieces = (_split_on(SUBSECTION_RE, body, label)
                      if len(body.split()) > max_words else [(label, body)])
            for sub_label, sub_text in pieces:
                units.extend(_chunk(sub_label or "budget text", sub_text, chunk_words))
    return [(label, body) for label, body in units if body.strip()]


def _pdf_text(contents):
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(contents))
    # Preserve line breaks so appropriation line items can be recognized.
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def load_budget(path=None, url=DEFAULT_BUDGET_URL, cache_dir="output/budget_sources"):
    """Read a local .txt/.pdf budget, or download/cache a budget PDF URL."""
    if path:
        source = Path(path)
        if not source.is_file():
            raise FileNotFoundError(f"Budget file does not exist: {source}")
        if source.suffix.lower() == ".pdf":
            text = _pdf_text(source.read_bytes())
        elif source.suffix.lower() == ".txt":
            text = source.read_text(encoding="utf-8-sig")
        else:
            raise ValueError("Budget file must be a .txt or .pdf")
        label = source.stem
        source_name = str(source)
    else:
        import requests
        source = Path(cache_dir) / Path(url.split("?", 1)[0]).name
        if source.suffix.lower() != ".pdf":
            raise ValueError("--budget-url must point to a PDF; use --budget for local text")
        if not source.is_file():
            response = requests.get(url, timeout=120)
            response.raise_for_status()
            if not response.content.startswith(b"%PDF"):
                raise ValueError(f"Expected a PDF at {url}")
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(response.content)
        text = _pdf_text(source.read_bytes())
        label = source.stem
        source_name = url
    if len(text.strip()) < 100:
        raise ValueError("Budget text is empty or too short; PDF may not be text-searchable")
    return label, source_name, text


def load_agenda_bills(path):
    """Read agenda bills with IDs and titles; skip no records silently."""
    records = []
    with open(path, encoding="utf-8") as f:
        for line_number, line in enumerate(f, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            id_value = record.get("bill_number") or record.get("docket_number")
            if not id_value:
                # The official docket URL can still identify unnumbered bills.
                match = re.search(r"/Bills/\d+/([HS]D?\d+)", record.get("bill_url") or "", re.I)
                id_value = match.group(1) if match else f"row{line_number}"
            records.append({
                "bill_number": norm_bill_id(id_value),
                "title": record.get("title") or "",
                "bill_url": record.get("bill_page_url") or record.get("bill_url") or "",
                "text": record.get("bill_text") or "",
            })
    return records


def summarize_sections(sections):
    scored = [s for s in sections if s["scored"]]
    word_count = sum(s["words"] for s in scored)
    strong = [s for s in scored if s["incorporated"]]
    partial = [s for s in scored if s["match_type"] in ("partial", "concepts only")]
    return {
        "sections_scored": len(scored),
        "sections_strong_match": len(strong),
        "pct_sections_strong_match": round(len(strong) / len(scored), 3) if scored else None,
        "pct_words_strong_match": round(sum(s["words"] for s in strong) / word_count, 3) if word_count else None,
        "pct_words_partial": round(sum(s["words"] for s in partial) / word_count, 3) if word_count else None,
        "verbatim": sum(s["match_type"] == "verbatim" for s in scored),
        "reworded": sum(s["match_type"] == "reworded" for s in scored),
        "concepts_only": sum(s["match_type"] == "concepts only" for s in scored),
        "partial": sum(s["match_type"] == "partial" for s in scored),
        "not_found": sum(s["match_type"] == "not found" for s in scored),
    }


def run_matching(bills, budget_text, budget_id, budget_source, embedder, args):
    budget_units = split_budget_sections(budget_text)
    target_index = prepare_budget_target(budget_text, budget_units, embedder)
    print(f"Indexed {len(budget_units)} budget units (+ neighbor windows)")
    summary, sections = [], []
    for i, bill in enumerate(bills, 1):
        base = {
            "bill_number": bill["bill_number"],
            "bill_title": bill["title"],
            "bill_url": bill["bill_url"],
            "budget_id": budget_id,
            "budget_source": budget_source,
        }
        if not str(bill["text"]).strip():
            summary.append({**base, "status": "missing bill text"})
            continue
        results = match_budget_pair(bill["text"], target_index, embedder, args)
        sections.extend({**base, **result} for result in results)
        summary.append({**base, "status": "ok" if any(s["scored"] for s in results) else "no scorable sections",
                        **summarize_sections(results)})
        print(f"{i}/{len(bills)} {bill['bill_number']}: "
              f"{summary[-1]['sections_strong_match']}/{summary[-1]['sections_scored']} strong sections")
    return pd.DataFrame(summary), pd.DataFrame(sections)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bills", default="output/agenda_bills.jsonl", help="agenda bills JSONL (or all_bills.jsonl)")
    p.add_argument("--budget", help="local budget .txt or .pdf; overrides --budget-url")
    p.add_argument("--budget-url", default=DEFAULT_BUDGET_URL,
                   help="PDF URL used if --budget is not provided (default H.5555 FY27)")
    p.add_argument("--budget-cache", default="output/budget_sources")
    p.add_argument("--out", default="output")
    p.add_argument("--limit", type=int, help="first N bills, for a trial run")
    p.add_argument("--no-embed", action="store_true", help="skip semantic model; lexical + concepts only")
    p.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2")
    # Same defaults as merge_match.py.
    p.add_argument("--lex-threshold", type=float, default=0.50)
    p.add_argument("--sem-threshold", type=float, default=0.80)
    p.add_argument("--concept-threshold", type=float, default=0.80)
    p.add_argument("--reworded-min-words", type=float, default=0.15)
    p.add_argument("--partial-threshold", type=float, default=0.70)
    args = p.parse_args(argv)
    bills = load_agenda_bills(args.bills)
    if args.limit is not None:
        if args.limit < 1:
            p.error("--limit must be at least 1")
        bills = bills[:args.limit]
    print(f"Loaded {len(bills)} bills from {args.bills}")
    budget_id, budget_source, budget_text = load_budget(args.budget, args.budget_url, args.budget_cache)
    print(f"Loaded budget {budget_id}: {len(budget_text):,} characters from {budget_source}")
    embedder = None if args.no_embed else Embedder(args.model)
    summary, sections = run_matching(bills, budget_text, budget_id, budget_source, embedder, args)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out / "budget_scores.csv", index=False)
    sections.to_csv(out / "budget_sections.csv", index=False)
    print(f"Wrote {len(summary)} bill scores and {len(sections)} section matches to {out}")


if __name__ == "__main__":
    main()
