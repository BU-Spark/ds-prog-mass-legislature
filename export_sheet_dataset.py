
import csv
import json
from pathlib import Path

INPUT = Path("output/agenda_bills.jsonl")
OUTPUT = Path("output/legislative_actions.csv")

HEADERS = [
    "Date",
    "Branch",
    "Bill Name",
    "Bill Number",
    "Bill Content",
    "Stage",
    "Action",
    "Related Bill",
    "Sources",
]


def derive_stage(action):
    """Infer a broad stage while preserving the full action separately."""
    text = (action or "").lower()

    rules = [
        (("introduced", "filed"), "Introduced"),
        (("referred to the committee", "referred to committee"), "Referred"),
        (("hearing scheduled", "hearing held", "public hearing"), "Hearing"),
        (("reported favorably", "reported adversely", "reported by committee",
          "ought to pass", "ought not to pass"), "Reported"),
        (("passed to be engrossed", "engrossed"), "Engrossed"),
        (("passed to be enacted", "enacted"), "Enacted"),
        (("signed by the governor", "became law"), "Signed into law"),
        (("concurred",), "Concurred"),
        (("accompanied",), "Accompanied"),
        (("merged", "consolidated"), "Merged"),
        (("discharged",), "Discharged"),
        (("reporting date extended", "extended"), "Extension"),
        (("second reading",), "Second Reading"),
        (("third reading",), "Third Reading"),
    ]

    for phrases, stage in rules:
        if any(phrase in text for phrase in phrases):
            return stage

    return "Other"


def main():
    if not INPUT.exists():
        raise FileNotFoundError(
            f"Cannot find {INPUT}. Run this script from your project root."
        )

    rows = []
    review = []

    with INPUT.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue

            record = json.loads(line)
            history = record.get("history") or []

            if not history:
                review.append({
                    "line": line_number,
                    "bill_number": record.get("bill_number"),
                    "issue": "No history entries",
                })
                continue

            bill_url = (
                record.get("bill_page_url")
                or record.get("bill_url")
                or ""
            )

            for event in history:
                related = event.get("related_bill") or ""

                if isinstance(related, list):
                    related = " / ".join(str(item) for item in related)

                action = event.get("action") or ""

                rows.append({
                    "Date": event.get("date") or "",
                    "Branch": event.get("branch") or "",
                    "Bill Name": record.get("title") or "",
                    "Bill Number": record.get("bill_number") or "",
                    "Bill Content": bill_url,
                    "Stage": derive_stage(action),
                    "Action": action,
                    "Related Bill": related,
                    "Sources": (
                        record.get("history_url")
                        or record.get("bill_url")
                        or ""
                    ),
                })

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    # utf-8-sig helps Excel recognize UTF-8 text correctly.
    with OUTPUT.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Action rows exported: {len(rows)}")
    print(f"Output file: {OUTPUT}")
    print(f"Bills needing review: {len(review)}")

    if review:
        review_path = OUTPUT.with_name("legislative_actions_review.json")
        review_path.write_text(
            json.dumps(review, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"Review log: {review_path}")


if __name__ == "__main__":
    main()
