import csv
import json
import time
from pathlib import Path

from scraper import scrape_bill
from crawl_related_bills import (
    bill_key,
    bill_url_for_reference,
    normalize_reference,
    read_jsonl,
    source_reference,
    split_references,
)

OUTPUT_DIR = Path("output")
BILLS_FILE = OUTPUT_DIR / "all_bills.jsonl"
RELATIONSHIPS_FILE = OUTPUT_DIR / "bill_relationships.csv"
REPORT_FILE = OUTPUT_DIR / "related_bill_crawl_report.json"
RECOVERY_REPORT = OUTPUT_DIR / "retry_failed_bills_report.json"

RELATIONSHIP_COLUMNS = [
    "source_bill",
    "related_bill",
    "relationship_type",
    "action_date",
    "branch",
    "action",
    "source_url",
]


def relationship_rows(bill):
    """Build relationship rows from a bill's history."""
    rows = []

    for event in bill.get("history") or []:
        for related in split_references(event.get("related_bill")):
            rows.append({
                "source_bill": source_reference(bill),
                "related_bill": related,
                "relationship_type": "history_reference",
                "action_date": event.get("date"),
                "branch": event.get("branch"),
                "action": event.get("action"),
                "source_url": (
                    bill.get("history_url") or bill.get("bill_url")
                ),
            })

    return rows


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    report = json.loads(REPORT_FILE.read_text(encoding="utf-8"))
    bills = read_jsonl(BILLS_FILE)

    bills_by_key = {
        bill_key(bill): bill
        for bill in bills
        if bill_key(bill)
    }

    # Retry only references that can be mapped to official bill URLs.
    failed = {}
    for error in report.get("errors", []):
        reference = normalize_reference(error.get("reference"))
        if reference:
            url = bill_url_for_reference(reference)
            if url:
                failed[reference] = url

    # Read and preserve existing relationship rows.
    with RELATIONSHIPS_FILE.open(
        "r", encoding="utf-8-sig", newline=""
    ) as file:
        reader = csv.DictReader(file)
        existing_rows = list(reader)

    def row_key(row):
        return tuple(str(row.get(col) or "") for col in RELATIONSHIP_COLUMNS)

    seen_relationships = {row_key(row) for row in existing_rows}
    relationship_rows_added = 0

    succeeded = []
    still_failed = []

    print(f"Unique bill references to retry: {len(failed)}")

    for index, (reference, url) in enumerate(failed.items(), start=1):
        print(f"[{index}/{len(failed)}] Retrying {reference}")

        try:
            time.sleep(1)
            bill = scrape_bill(url)

            key = bill_key(bill)
            if not key:
                raise ValueError("Scraped bill has no usable identity")

            bills_by_key[key] = bill
            succeeded.append(reference)

            for row in relationship_rows(bill):
                identity = row_key(row)
                if identity not in seen_relationships:
                    existing_rows.append(row)
                    seen_relationships.add(identity)
                    relationship_rows_added += 1

        except Exception as exc:
            still_failed.append({
                "reference": reference,
                "url": url,
                "error": str(exc),
            })

    # Save recovered bills.
    with BILLS_FILE.open("w", encoding="utf-8", newline="\n") as file:
        for bill in bills_by_key.values():
            file.write(json.dumps(bill, ensure_ascii=False) + "\n")

    # Save preserved and newly discovered relationships.
    with RELATIONSHIPS_FILE.open(
        "w", encoding="utf-8-sig", newline=""
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=RELATIONSHIP_COLUMNS,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(existing_rows)

    recovery = {
        "attempted": len(failed),
        "succeeded": len(succeeded),
        "still_failed": len(still_failed),
        "relationship_rows_added": relationship_rows_added,
        "succeeded_references": succeeded,
        "errors": still_failed,
    }

    RECOVERY_REPORT.write_text(
        json.dumps(recovery, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Recovered bills: {len(succeeded)}")
    print(f"Still failing: {len(still_failed)}")
    print(f"New relationship rows: {relationship_rows_added}")
    print(f"Recovery report: {RECOVERY_REPORT}")


if __name__ == "__main__":
    main()
