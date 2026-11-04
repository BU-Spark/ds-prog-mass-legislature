"""
refetch_bill_text.py - Re-scrape bill_text in output/all_bills.jsonl with the fixed
duplicate check in scraper.extract_bill_text. Nothing else in each record changes.

The old check cut text at any later "Section 1." (case-insensitive), so bills that
insert a new chapter of law lost everything after the chapter heading. A cut bill can
be any length, so the safe fix is to re-fetch every bill (~15 min at 1 request/second).

Run from the repo root:
  python refetch_bill_text.py --limit 10     # try 10 first
  python refetch_bill_text.py                # all bills
  python refetch_bill_text.py --only-short   # just bills under 50 words

Writes:
  output/all_bills.jsonl                   updated in place
  output/all_bills.before_refetch.jsonl    backup of the original (made once)
  output/refetch_report.csv                old vs new word count per bill
"""

import argparse
import csv
import json
import shutil
import time
from pathlib import Path

from scraper import extract_bill_text

DELAY_SECONDS = 1  # team rule: keep the 1-second delay


def words(text):
    return len(str(text or "").split())


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bills", default="output/all_bills.jsonl")
    p.add_argument("--limit", type=int, help="only re-fetch the first N bills")
    p.add_argument("--only-short", action="store_true", help="only bills under 50 words")
    args = p.parse_args()

    path = Path(args.bills)
    backup = path.with_name(path.stem + ".before_refetch.jsonl")
    if not backup.exists():
        shutil.copy(path, backup)
        print(f"Backup saved to {backup}")

    bills = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    todo = [i for i, b in enumerate(bills) if b.get("bill_text_url")]
    if args.only_short:
        todo = [i for i in todo if words(bills[i].get("bill_text")) < 50]
    if args.limit:
        todo = todo[: args.limit]
    print(f"Re-fetching {len(todo)} of {len(bills)} bills (about {len(todo) * (DELAY_SECONDS + 0.5) / 60:.0f} min)")

    report = []
    for n, i in enumerate(todo, 1):
        b = bills[i]
        old = b.get("bill_text")
        try:
            new = extract_bill_text(b["bill_text_url"])
            status = "ok" if new else "empty, kept old"
        except Exception as e:  # keep going; one bad page shouldn't stop the run
            new, status = None, f"error: {e}"
        if new:
            b["bill_text"] = new
        report.append({"bill_number": b.get("bill_number"), "old_words": words(old),
                       "new_words": words(new) if new else words(old), "status": status})
        if n % 50 == 0:
            print(f"  {n}/{len(todo)}")
        time.sleep(DELAY_SECONDS)

    with path.open("w") as f:
        for b in bills:
            f.write(json.dumps(b, ensure_ascii=False) + "\n")

    out = path.with_name("refetch_report.csv")
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["bill_number", "old_words", "new_words", "status"])
        w.writeheader()
        w.writerows(report)

    grew = [r for r in report if r["new_words"] > r["old_words"]]
    errors = [r for r in report if r["status"].startswith("error")]
    print(f"Done. {len(grew)} bills got longer, {len(errors)} errors. Details in {out}")
    for r in sorted(grew, key=lambda r: r["new_words"] - r["old_words"], reverse=True)[:10]:
        print(f"  {r['bill_number']}: {r['old_words']} -> {r['new_words']} words")


if __name__ == "__main__":
    main()
