
import json
import re
from io import BytesIO

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader


BASE_URL = "https://malegislature.gov"

# Test bill. This is the House Docket No. 3390 page.
BILL_URL = f"{BASE_URL}/Bills/194/HD3390"


def get_soup(url):
    """Download a webpage and return its parsed HTML."""
    response = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def get_text(element):
    """Return cleaned text from an HTML element."""
    if element is None:
        return None

    text = element.get_text(" ", strip=True)
    return text or None


def extract_bill_metadata(soup, bill_url):
    """Extract the main bill details and related URLs."""
    # Find the heading containing the bill number.
    heading = soup.find(
        lambda tag: tag.name in ("h1", "h2", "h3")
        and re.search(r"\b[HS]\.\s*\d+", tag.get_text(" ", strip=True))
    )

    bill_number = None
    if heading:
        match = re.search(
            r"\b([HS])\.\s*(\d+)",
            heading.get_text(" ", strip=True),
        )
        if match:
            bill_number = f"{match.group(1)}.{match.group(2)}"

    # Extract the bill title from the heading's parent.
    title = None
    if heading and heading.parent:
        follow_link = heading.parent.find("a")

        if follow_link:
            aria_label = follow_link.get("aria-label", "")
            prefix = "Follow in MyLegislature: "

            if aria_label.startswith(prefix):
                title = aria_label.replace(prefix, "", 1).strip()

    # The bill description is in the bill information section.
    description = None
    presenter = None

    bill_info = soup.find("dl", class_="billInfo")
    if bill_info:
        # Find the description paragraph, excluding the presenter label.
        description_element = soup.find(
            string=re.compile(
                r"By Representative|By Senator",
                flags=re.IGNORECASE,
            )
        )

        if description_element:
            description = get_text(description_element.parent)

        presenter_link = bill_info.find("a", href=True)
        if presenter_link:
            presenter = get_text(presenter_link)

    # Use the docket page to find the actual bill number in its links.
    # For example, HD3390 is the docket; H3110 is the bill.
    bill_path = None

    if bill_number:
        branch_letter = bill_number[0]
        number = bill_number.split(".")[1]
        bill_path = f"{branch_letter}{number}"

    if not bill_path:
        match = re.search(r"/Bills/(\d+)/([HS])D?(\d+)", bill_url)
        if match:
            bill_path = f"{match.group(2)}{match.group(3)}"

    # Prefer the bill-number link from the page when available.
    if bill_path:
        bill_page_url = f"{BASE_URL}/Bills/194/{bill_path}"
    else:
        bill_page_url = bill_url

    # The PDF and related pages use the actual bill number, not the docket.
    if bill_number:
        branch_letter = bill_number[0]
        number = bill_number.split(".")[1]
        bill_path = f"{branch_letter}{number}"

    pdf_url = f"{BASE_URL}/Bills/194/{bill_path}.pdf"
    bill_text_url = (
        f"{BASE_URL}/Bills/194/{bill_path}/"
        f"{'House' if bill_path.startswith('H') else 'Senate'}/Bill/Text"
    )
    history_url = f"{BASE_URL}/Bills/194/{bill_path}/BillHistory"

    # Use the bill number from the source when possible.
    # A missing field should be visible rather than silently guessed.
    return {
        "bill_number": bill_number,
        "title": title,
        "description": description,
        "presenter": presenter,
        "bill_url": bill_url,
        "bill_text_url": bill_text_url,
        "pdf_url": pdf_url,
        "history_url": history_url,
    }


def extract_filed_date(pdf_url):
    """Extract the filing date from the bill PDF's first page."""
    response = requests.get(
        pdf_url,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    response.raise_for_status()

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

    from datetime import datetime

    return datetime.strptime(match.group(1), "%m/%d/%Y").date().isoformat()


    """Extract the full bill text, starting at SECTION 1."""
    soup = get_soup(text_url)

    paragraphs = soup.find_all("p")

    start_index = None
    for index, paragraph in enumerate(paragraphs):
        text = get_text(paragraph) or ""
        if re.search(r"\bSECTION\s+1\.", text, flags=re.IGNORECASE):
            start_index = index
            break

    if start_index is None:
        return None

    bill_paragraphs = []

    for paragraph in paragraphs[start_index:]:
        text = get_text(paragraph)
        if not text:
            continue

        # Stop at the site's disclaimer or page footer.
        if "Massachusetts General Court" in text and "disclaimer" in text.lower():
            break

        bill_paragraphs.append(text)

    return "\n\n".join(bill_paragraphs) if bill_paragraphs else None


def extract_bill_text(text_url):
    """Extract bill text and remove a repeated copy if present."""
    soup = get_soup(text_url)

    # Find the paragraph containing SECTION 1.
    start_paragraph = None

    for paragraph in soup.find_all("p"):
        text = paragraph.get_text(" ", strip=True)
        if "SECTION 1." in text:
            start_paragraph = paragraph
            break

    if start_paragraph is None:
        return None

    # Collect text from the starting paragraph and following paragraphs.
    paragraphs = [start_paragraph]
    paragraphs.extend(start_paragraph.find_all_next("p"))

    parts = []
    for paragraph in paragraphs:
        text = paragraph.get_text(" ", strip=True)

        if "The information contained in this website" in text:
            break

        if text:
            parts.append(text)

    full_text = "\n\n".join(parts)

    # If the complete bill appears twice, retain only the first copy.
    # The repeated copy starts at the second SECTION 1 heading.
    headings = list(re.finditer(r"\bSECTION\s+1\.", full_text))

    if len(headings) >= 2:
        full_text = full_text[:headings[1].start()].strip()

    return full_text or None

def extract_bill_history(history_url):
    """Extract dated actions from the bill history table."""
    soup = get_soup(history_url)

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

        related_bill = None

        for link in cells[2].find_all("a", href=True):
            href = link["href"]

            if "/Bills/" in href:
                related_bill = link.get_text(strip=True)
                break

        history.append(
            {
                "date": date,
                "branch": branch,
                "action": action,
                "related_bill": related_bill,
            }
        )

    return history


def scrape_bill(bill_url):
    """Collect bill metadata, filing date, text, and history."""
    soup = get_soup(bill_url)
    bill = extract_bill_metadata(soup, bill_url)

    if bill is None:
        raise ValueError(f"Could not extract bill metadata from {bill_url}")

    bill["filed_date"] = extract_filed_date(bill["pdf_url"])
    bill["bill_text"] = extract_bill_text(bill["bill_text_url"])
    bill["history"] = extract_bill_history(bill["history_url"])

    return bill


def main():
    bill = scrape_bill(BILL_URL)

    output_file = "bill.json"

    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(bill, file, indent=2, ensure_ascii=False)

    print(json.dumps(bill, indent=2, ensure_ascii=False))
    print(f"\nSaved bill data to {output_file}")
    print(f"History actions extracted: {len(bill['history'])}")


if __name__ == "__main__":
    main()