
import csv
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, urldefrag

import requests


AGENDA_URL = (
    "https://www.progressivemass.com/"
    "2025-2026-legislative-agenda/"
)

OUTPUT_FILE = "agenda_bill_urls.csv"


class AgendaLinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.current_url = None
        self.current_text = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            attrs = dict(attrs)
            href = attrs.get("href")

            if href:
                self.current_url = href
                self.current_text = []

    def handle_data(self, data):
        if self.current_url is not None:
            self.current_text.append(data.strip())

    def handle_endtag(self, tag):
        if tag == "a" and self.current_url is not None:
            self.links.append(
                (
                    " ".join(
                        part for part in self.current_text if part
                    ),
                    self.current_url,
                )
            )
            self.current_url = None
            self.current_text = []


def main():
    response = requests.get(
        AGENDA_URL,
        timeout=30,
        headers={"User-Agent": "MassLegislatureResearch/1.0"},
    )
    response.raise_for_status()

    parser = AgendaLinkParser()
    parser.feed(response.text)

    bills = {}

    for link_text, href in parser.links:
        absolute_url = urljoin(AGENDA_URL, href)
        absolute_url, _ = urldefrag(absolute_url)
        parsed = urlparse(absolute_url)

        if parsed.hostname not in {
            "malegislature.gov",
            "www.malegislature.gov",
        }:
            continue

        match = re.search(
            r"/Bills/(\d+)/(HD|SD|H|S)\.?(\d+)",
            parsed.path,
            re.IGNORECASE,
        )

        if not match:
            continue

        session, chamber_prefix, number = match.groups()
        bill_id = f"{chamber_prefix.upper()}.{number}"

        # Keep one URL per distinct bill identifier.
        bills.setdefault(
            bill_id,
            {
                "bill_id": bill_id,
                "session": session,
                "link_text": link_text,
                "url": absolute_url,
            },
        )

    with open(
        OUTPUT_FILE,
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "bill_id",
                "session",
                "link_text",
                "url",
            ],
        )
        writer.writeheader()
        writer.writerows(
            sorted(
                bills.values(),
                key=lambda bill: (
                    bill["chamber_prefix"]
                    if "chamber_prefix" in bill
                    else bill["bill_id"].split(".")[0],
                    int(bill["bill_id"].split(".")[1]),
                ),
            )
        )

    print(f"Agenda page: {AGENDA_URL}")
    print(f"Unique linked bills: {len(bills)}")
    print(f"Saved inventory to: {OUTPUT_FILE}")

    for bill in sorted(bills):
        print(f"{bill}: {bills[bill]['url']}")


if __name__ == "__main__":
    main()