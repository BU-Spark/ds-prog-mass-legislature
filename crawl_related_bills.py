"""Recursively crawl agenda bills and their related bills.

Keeps the original agenda scrape and dataset export unchanged.
"""

import argparse
import csv
import json
import re
from collections import deque
from pathlib import Path
from urllib.parse import urljoin
import time

from scraper import BASE_URL, scrape_bill


INPUT_FILE = Path("output/agenda_bills.jsonl")
OUTPUT_DIR = Path("output")

ALL_BILLS_FILE = OUTPUT_DIR / "all_bills.jsonl"
RELATIONSHIPS_FILE = OUTPUT_DIR / "bill_relationships.csv"
REPORT_FILE = OUTPUT_DIR / "related_bill_crawl_report.json"


def read_jsonl(path):
    """Read JSON Lines into a list of dictionaries."""
    records = []

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue

            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON in {path}, line {line_number}: {exc}"
                ) from exc

    return records


def write_jsonl(path, records):
    """Write dictionaries as JSON Lines."""
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for record in records:
            file.write(
                json.dumps(record, ensure_ascii=False) + "\n"
            )


def normalize_reference(reference):
    """Normalize a single formal bill reference or docket identifier."""
    if not reference:
        return None

    value = reference.strip().upper()
    value = re.sub(r"\s+", "", value)

    # Formal references: H3591, H.3591, S2696, S.2696.
    match = re.fullmatch(r"([HS])\.?(\d+)", value)
    if match:
        return f"{match.group(1)}{match.group(2)}"

    # Docket identifiers must remain docket identifiers.
    match = re.fullmatch(r"([HS][DS])(\d+)", value)
    if match:
        return f"{match.group(1)}{match.group(2)}"

    return None


def split_references(value):
    """Split a history field such as 'H3591 / H3598' into identifiers."""
    if not value:
        return []

    references = []

    # First split the field as emitted by extract_bill_history.
    for piece in value.split("/"):
        normalized = normalize_reference(piece)
        if normalized and normalized not in references:
            references.append(normalized)

    return references


def bill_url_for_reference(reference):
    """Construct the official bill page URL for a normalized reference."""
    normalized = normalize_reference(reference)
    if not normalized:
        return None

    return f"{BASE_URL}/Bills/194/{normalized}"


def bill_key(bill):
    """Return a stable identity for a scraped bill."""
    formal_number = normalize_reference(bill.get("bill_number"))
    if formal_number:
        return formal_number

    docket_number = normalize_reference(bill.get("docket_number"))
    if docket_number:
        return docket_number

    return bill.get("bill_url") or bill.get("bill_page_url")


def source_reference(bill):
    """Return a source label for relationship records."""
    return (
        normalize_reference(bill.get("bill_number"))
        or normalize_reference(bill.get("docket_number"))
        or bill.get("bill_url")
        or ""
    )


def crawl(max_bills=None):
    """Crawl agenda bills and recursively follow formal bill references."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Missing {INPUT_FILE}. Run scrape_agenda.py first."
        )

    seed_bills = read_jsonl(INPUT_FILE)

    bills_by_key = {}
    queue = deque()
    relationships = []
    unresolved = []
    deferred = []
    errors = []

    # Seed the crawl with the agenda records already scraped.
    for bill in seed_bills:
        key = bill_key(bill)
        if not key:
            errors.append({
                "stage": "seed",
                "error": "Agenda record has no usable bill identity",
                "bill": bill,
            })
            continue

        if key not in bills_by_key:
            bills_by_key[key] = bill
            queue.append((key, bill.get("bill_url"), bill))

    processed = set()

    while queue:
        key, url, existing_record = queue.popleft()

        if key in processed:
            continue

        if max_bills is not None and len(processed) >= max_bills:
            deferred.append({
                "reference": key,
                "reason": f"Maximum bill limit reached ({max_bills})",
            })
            continue


        processed.add(key)

        # Seed records already contain their full metadata and history.
        # Related records are scraped on discovery before being queued.
        bill = existing_record

        if not bill.get("history") and url and key not in {
            bill_key(seed) for seed in seed_bills
        }:
            try:
                time.sleep(0.5)
                bill = scrape_bill(url)
                bills_by_key[key] = bill
            except Exception as exc:
                errors.append({
                    "reference": key,
                    "url": url,
                    "error": str(exc),
                })
                continue

        history = bill.get("history") or []

        for event in history:
            raw_related = event.get("related_bill")
            related_references = split_references(raw_related)

            if raw_related and not related_references:
                unresolved.append({
                    "source_bill": source_reference(bill),
                    "reference": raw_related,
                    "action": event.get("action"),
                    "reason": "Could not normalize related reference",
                })

            for related in related_references:
                relationship = {
                    "source_bill": source_reference(bill),
                    "related_bill": related,
                    "relationship_type": "history_reference",
                    "action_date": event.get("date"),
                    "branch": event.get("branch"),
                    "action": event.get("action"),
                    "source_url": bill.get("history_url") or bill.get("bill_url"),
                }
                relationships.append(relationship)

                if related in bills_by_key or related in processed:
                    continue

                related_url = bill_url_for_reference(related)
                if not related_url:
                    unresolved.append({
                        "source_bill": source_reference(bill),
                        "reference": related,
                        "reason": "No official URL could be constructed",
                    })
                    continue

                # Scrape now so a bad link is recorded as an error rather
                # than being silently dropped from the crawl.
                try:
                    related_bill = scrape_bill(related_url)
                except Exception as exc:
                    errors.append({
                        "reference": related,
                        "url": related_url,
                        "source_bill": source_reference(bill),
                        "error": str(exc),
                    })
                    continue

                discovered_key = bill_key(related_bill)
                if not discovered_key:
                    unresolved.append({
                        "source_bill": source_reference(bill),
                        "reference": related,
                        "url": related_url,
                        "reason": "Scraped record has no usable identity",
                    })
                    continue

                bills_by_key[discovered_key] = related_bill
                queue.append((discovered_key, related_url, related_bill))

    # Write all discovered bills, including those whose histories are empty.
    write_jsonl(ALL_BILLS_FILE, bills_by_key.values())

    relationship_columns = [
        "source_bill",
        "related_bill",
        "relationship_type",
        "action_date",
        "branch",
        "action",
        "source_url",
    ]

    with RELATIONSHIPS_FILE.open(
        "w", encoding="utf-8-sig", newline=""
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=relationship_columns,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(relationships)

    report = {
        "seed_file": str(INPUT_FILE),
        "seed_bill_count": len(seed_bills),
        "unique_bills_saved": len(bills_by_key),
        "bills_processed": len(processed),
        "relationship_rows": len(relationships),
        "unresolved_reference_count": len(unresolved),
        "error_count": len(errors),
        "max_bills": max_bills,
        "deferred_reference_count": len(deferred),
        "deferred_references": deferred,
        "unresolved_references": unresolved,
        "errors": errors,
        "outputs": {
            "bills": str(ALL_BILLS_FILE),
            "relationships": str(RELATIONSHIPS_FILE),
        },
    }

    REPORT_FILE.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Agenda seed records: {len(seed_bills)}")
    print(f"Unique bills saved: {len(bills_by_key)}")
    print(f"Bills processed: {len(processed)}")
    print(f"Relationships written: {len(relationships)}")
    print(f"Unresolved references: {len(unresolved)}")
    print(f"Errors: {len(errors)}")
    print(f"Saved bills to: {ALL_BILLS_FILE}")
    print(f"Saved relationships to: {RELATIONSHIPS_FILE}")
    print(f"Saved report to: {REPORT_FILE}")


def main():
    parser = argparse.ArgumentParser(
        description="Recursively crawl related Massachusetts legislative bills."
    )
    parser.add_argument(
        "--max-bills",
        type=int,
        default=500,
        help="Maximum bills to process (default: 500). Use 0 for no limit.",
    )
    args = parser.parse_args()

    if args.max_bills < 0:
        parser.error("--max-bills must be zero or greater")

    crawl(max_bills=args.max_bills or None)


if __name__ == "__main__":
    main()
