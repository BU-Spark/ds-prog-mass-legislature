
import csv
import json
import time
from pathlib import Path

from scraper import scrape_bill


INPUT_FILE = Path("agenda_bill_urls.csv")
OUTPUT_DIR = Path("output")
JSONL_FILE = OUTPUT_DIR / "agenda_bills.jsonl"
ERROR_FILE = OUTPUT_DIR / "agenda_errors.jsonl"


def read_bill_urls(path):
    """Read bill URLs from the agenda inventory CSV."""
    urls = []

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        # Accept common column names used for URLs.
        url_column = next(
            (
                name
                for name in (reader.fieldnames or [])
                if name and name.strip().lower() in {
                    "url", "bill_url", "bill_link", "link"
                }
            ),
            None,
        )

        if url_column is None:
            raise ValueError(
                f"Could not find a URL column in {path}. "
                f"Columns found: {reader.fieldnames}"
            )

        for row in reader:
            url = (row.get(url_column) or "").strip()
            if url and url not in urls:
                urls.append(url)

    return urls


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Missing {INPUT_FILE}. Run discover_agenda_bills.py first."
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    urls = read_bill_urls(INPUT_FILE)

    print(f"Found {len(urls)} unique bill URLs.")

    successful = 0
    failed = 0

    with JSONL_FILE.open("w", encoding="utf-8") as output, \
         ERROR_FILE.open("w", encoding="utf-8") as errors:

        for index, url in enumerate(urls, start=1):
            print(f"[{index}/{len(urls)}] Scraping {url}")

            try:
                bill = scrape_bill(url)

                # Preserve the original agenda URL, even if bill metadata
                # identifies a different, official bill-number page.
                bill["agenda_source_url"] = url

                output.write(
                    json.dumps(bill, ensure_ascii=False) + "\n"
                )
                output.flush()

                successful += 1
                print(
                    f"  OK: bill_number={bill.get('bill_number')!r}, "
                    f"title={bill.get('title')!r}, "
                    f"history_actions={len(bill.get('history', []))}"
                )

            except Exception as exc:
                failed += 1
                error_record = {
                    "agenda_source_url": url,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                errors.write(
                    json.dumps(error_record, ensure_ascii=False) + "\n"
                )
                errors.flush()
                print(f"  ERROR: {type(exc).__name__}: {exc}")

            # Be polite to the legislature website.
            time.sleep(1)

    print("\nScraping finished.")
    print(f"URLs found: {len(urls)}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Bill data: {JSONL_FILE}")
    print(f"Errors: {ERROR_FILE}")


if __name__ == "__main__":
    main()