import json
import re
from datetime import datetime
from io import BytesIO
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
import time
from requests.exceptions import ConnectionError, Timeout


BASE_URL = "https://malegislature.gov"

# Test bill: House Docket No. 3390
BILL_URL = f"{BASE_URL}/Bills/194/HD3390"


def download_response(url, max_attempts=4):
    """Download a URL, retrying temporary connection failures."""
    for attempt in range(max_attempts):
        try:
            response = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=30,
            )
            response.raise_for_status()
            return response
        except (ConnectionError, Timeout):
            if attempt == max_attempts - 1:
                raise

            delay = 2 ** attempt
            print(
                f"Request failed; retrying in {delay}s "
                f"({attempt + 1}/{max_attempts}): {url}"
            )
            time.sleep(delay)


def get_soup(url):
    """Download a webpage and return its parsed HTML."""
    if not url:
        return None

    response = download_response(url)
    return BeautifulSoup(response.text, "html.parser")



def get_text(element):
    """Return cleaned text from an HTML element."""
    if element is None:
        return None

    text = element.get_text(" ", strip=True)
    return text or None


def extract_bill_metadata(soup, bill_url):
    """Extract bill details and related URLs from a bill or docket page."""

    docket_match = re.search(
        r"/Bills/\d+/(H[DS]\d+|S[DS]\d+)(?:/|$)",
        bill_url,
        flags=re.IGNORECASE,
    )
    docket_number = docket_match.group(1).upper() if docket_match else None
    # Find a heading containing an assigned bill number, such as H.3110.
    # Docket numbers such as HD4328 must not be mistaken for bill numbers.
    heading = soup.find(
        lambda tag: tag.name in ("h1", "h2", "h3")
        and re.search(
            r"\b[HS]\.\s*\d+",
            tag.get_text(" ", strip=True),
        )
    )


    bill_number = None

    if heading:
        match = re.search(
            r"\b([HS])\.\s*(\d+)",
            heading.get_text(" ", strip=True),
        )
        if match:
            bill_number = f"{match.group(1)}.{match.group(2)}"

    # Extract the title from the assigned bill's follow link when available.
    title = None

    if heading and heading.parent:
        for link in heading.parent.find_all("a", href=True):
            aria_label = link.get("aria-label", "")
            prefix = "Follow in MyLegislature: "

            if aria_label.startswith(prefix):
                title = aria_label[len(prefix):].strip()
                break

    # Generic fallback for docket pages and pages without a follow-link title.
    if not title:
        for tag in soup.find_all(["h1", "h2", "h3"]):
            candidate = get_text(tag)

            if not candidate:
                continue

            if re.search(r"\b[HS]\.\s*\d+", candidate):
                continue

            if re.match(
                r"^(an act|resolve|resolution|order|petition)\b",
                candidate,
                flags=re.IGNORECASE,
            ):
                title = candidate
                break


    # Extract the description and presenter from the bill information section.
    description = None
    presenter = None

    bill_info = soup.find("dl", class_="billInfo")

    if bill_info:
        # Find the element containing the bill's introductory description.
        description_pattern = re.compile(
            r"\bBy\s+(?:Representative|Senator|Mr\.|Ms\.|Mrs\.|Miss)\b",
            flags=re.IGNORECASE,
        )

        for element in bill_info.find_all(["dd", "p", "div", "span"]):
            candidate = get_text(element)

            if candidate and description_pattern.search(candidate):
                description = candidate
                break

        # Fall back to searching the full bill information section.
        if not description:
            info_text = get_text(bill_info)
            match = description_pattern.search(info_text or "")

            if match:
                description = info_text[match.start():]

        # Extract the presenter independently from the description.
        presenter_link = bill_info.find("a", href=True)

        if presenter_link:
            presenter = get_text(presenter_link)


        # Only construct bill-number URLs when an assigned bill number was found.
        # Never convert a docket such as HD4328 into a guessed bill H4328.
        bill_path = None

        if bill_number:
            branch_letter = bill_number[0]
            number = bill_number.split(".")[1]
            bill_path = f"{branch_letter}{number}"

        pdf_url = None
        bill_text_url = None
        history_url = None

        if bill_path:
            bill_page_url = f"{BASE_URL}/Bills/194/{bill_path}"
            pdf_url = f"{bill_page_url}.pdf"

            branch = "House" if bill_path.startswith("H") else "Senate"

            bill_text_url = (
                f"{bill_page_url}/{branch}/Bill/Text"
            )
            history_url = f"{bill_page_url}/BillHistory"

        else:
            # For docket-only pages, use the official links found on that page.
            bill_page_url = bill_url

            for link in soup.find_all("a", href=True):
                label = (get_text(link) or "").lower()
                href = link["href"]

                if "view text" in label:
                    bill_text_url = urljoin(BASE_URL, href)

                elif "download pdf" in label:
                    pdf_url = urljoin(BASE_URL, href)

                elif "history" in label:
                    history_url = urljoin(BASE_URL, href)

    return {
        "bill_number": bill_number,
        "title": title,
        "description": description,
        "presenter": presenter,
        "bill_url": bill_url,
        "bill_page_url": bill_page_url,
        "bill_text_url": bill_text_url,
        "pdf_url": pdf_url,
        "history_url": history_url,
        "docket_number": docket_number,
    }


def extract_filed_date(pdf_url):
    """Extract the filing date from the first page of a bill PDF."""
    if not pdf_url:
        return None

    response = download_response(pdf_url)
    reader = PdfReader(BytesIO(response.content))

    if not reader.pages:
        return None

    first_page = reader.pages[0].extract_text() or ""

    match = re.search(
        r"FILED\s+ON:\s*(\d{1,2}/\d{1,2}/\d{4})",
        first_page,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    return datetime.strptime(
        match.group(1), "%m/%d/%Y"
    ).date().isoformat()


def extract_bill_text(text_url):
    """Extract bill text from the official bill text page."""
    if not text_url:
        return None

    soup = get_soup(text_url)

    if soup is None:
        return None

    paragraphs = soup.find_all("p")
    bill_paragraphs = []

    for paragraph in paragraphs:
        text = get_text(paragraph)

        if not text:
            continue

        # Stop at the website's footer or disclaimer.
        if "The information contained in this website" in text:
            break

        # Remove a leading bill label when present.
        text = re.sub(
            r"^×\s*Bill\s+[HS]\.\s*\d+\s*",
            "",
            text,
        ).strip()

        if text:
            bill_paragraphs.append(text)

    bill_text = "\n".join(bill_paragraphs).strip()

    if not bill_text:
        return None

    # Some pages repeat the bill text. Keep only the first complete copy.
    first_section = re.search(
        r"\bSECTION\s+1\.",
        bill_text,
        flags=re.IGNORECASE,
    )

    if first_section:
        remaining_text = bill_text[first_section.end():]

        second_section = re.search(
            r"\bSECTION\s+1\.",
            remaining_text,
            flags=re.IGNORECASE,
        )

        if second_section:
            duplicate_start = (
                first_section.end() + second_section.start()
            )
            bill_text = bill_text[:duplicate_start].strip()

    return bill_text or None


def extract_bill_history(history_url):
    """Extract dated actions and all related bill references."""
    if not history_url:
        return []

    soup = get_soup(history_url)

    if soup is None:
        return []

    table = soup.find("table", class_="table")

    if table is None:
        return []

    history = []

    for row in table.select("tbody tr"):
        cells = row.find_all("td", recursive=False)

        if len(cells) < 3:
            continue

        date = get_text(cells[0])
        branch = get_text(cells[1])
        action = cells[2].get_text(" ", strip=True)

        # Collect every bill link in the action cell.
        related_bills = []
        for link in cells[2].find_all("a", href=True):
            if "/Bills/" in link["href"]:
                bill_reference = get_text(link)
                if bill_reference and bill_reference not in related_bills:
                    related_bills.append(bill_reference)

        # Also detect bill numbers written as plain text, such as
        # "Accompanied by H3591 and H3598", when they are not links.
        import re

        bill_pattern = re.compile(
            r"\b(?:H|S)\.?\s*\d+\b",
            re.IGNORECASE
        )

        for match in bill_pattern.findall(action):
            normalized = re.sub(r"\s+", "", match).upper()
            if normalized not in related_bills:
                related_bills.append(normalized)

        history.append(
            {
                "date": date,
                "branch": branch,
                "action": action,
                "related_bill": " / ".join(related_bills) or None,
            }
        )

    return history


def scrape_bill(bill_url):
    """Collect bill metadata, filing date, text, and history."""
    soup = get_soup(bill_url)

    if soup is None:
        raise ValueError(f"Could not download bill page: {bill_url}")

    bill = extract_bill_metadata(soup, bill_url)

    if bill is None:
        raise ValueError(
            f"Could not extract bill metadata from {bill_url}"
        )

    # Missing optional URLs should not cause requests to fetch None.
    try:
        bill["filed_date"] = (
            extract_filed_date(bill["pdf_url"])
            if bill.get("pdf_url")
            else None
        )
    except (requests.RequestException, ValueError, OSError):
        bill["filed_date"] = None

    bill["bill_text"] = extract_bill_text(
        bill.get("bill_text_url")
    )

    bill["history"] = extract_bill_history(
        bill.get("history_url")
    )

    return bill


def main():
    bill = scrape_bill(BILL_URL)

    output_file = "bill.json"

    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(
            bill,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print(json.dumps(bill, indent=2, ensure_ascii=False))
    print(f"\nSaved bill data to {output_file}")
    print(f"History actions extracted: {len(bill['history'])}")


if __name__ == "__main__":
    main()
