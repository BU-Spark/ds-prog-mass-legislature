import csv
import json
import time
from pathlib import Path

from scraper import scrape_bill
from crawl_related_bills import bill_key
from retry_failed_bills import relationship_rows, RELATIONSHIP_COLUMNS

out = Path("output")
bills_file = out / "all_bills.jsonl"
relationships_file = out / "bill_relationships.csv"

references = ["H5293", "H5489", "S1519", "S1577", "S248", "S3241"]

bills = [
    b for b in (
        json.loads(line)
        for line in bills_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
]
bills_by_key = {bill_key(b): b for b in bills if bill_key(b)}

with relationships_file.open(
    encoding="utf-8-sig", newline=""
) as f:
    existing_rows = list(csv.DictReader(f))

def row_key(row):
    return tuple(str(row.get(c) or "") for c in RELATIONSHIP_COLUMNS)

seen = {row_key(r) for r in existing_rows}
added_bills = []
added_rows = 0
failures = []

for i, ref in enumerate(references, start=1):
    url = f"https://malegislature.gov/Bills/194/{ref}"
    print(f"[{i}/{len(references)}] Scraping {ref}")
    try:
        time.sleep(1)
        bill = scrape_bill(url)
        key = bill_key(bill)

        if not key:
            raise ValueError("Scraped record has no usable bill identity")

        if key not in bills_by_key:
            bills_by_key[key] = bill
            added_bills.append(ref)

        for row in relationship_rows(bill):
            identity = row_key(row)
            if identity not in seen:
                existing_rows.append(row)
                seen.add(identity)
                added_rows += 1

    except Exception as exc:
        failures.append({"reference": ref, "url": url, "error": str(exc)})
        print(f"  FAILED: {exc}")

with bills_file.open("w", encoding="utf-8", newline="\n") as f:
    for bill in bills_by_key.values():
        f.write(json.dumps(bill, ensure_ascii=False) + "\n")

with relationships_file.open(
    "w", encoding="utf-8-sig", newline=""
) as f:
    writer = csv.DictWriter(f, fieldnames=RELATIONSHIP_COLUMNS)
    writer.writeheader()
    writer.writerows(existing_rows)

(out / "missing_refs_recovery_report.json").write_text(
    json.dumps({
        "references_attempted": references,
        "new_bill_records": added_bills,
        "new_relationship_rows": added_rows,
        "failures": failures,
    }, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print("\nNew bill records:", len(added_bills))
print("New relationship rows:", added_rows)
print("Failures:", len(failures))
