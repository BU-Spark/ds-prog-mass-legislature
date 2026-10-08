import requests
from bs4 import BeautifulSoup
from datetime import datetime

URL = "https://malegislature.gov/Bills/194/HD3390"

response = requests.get(URL, timeout=10)
response.raise_for_status()

soup = BeautifulSoup(response.text, "html.parser")

heading = soup.find("h1")
'''<h1>
                        Bill H.3110 
                        <span class="subTitle">194th (Current)</span>
</h1>'''

# Bill number
bill_text = heading.find(string=True, recursive=False).strip()
#bill_text = Bill H.3110
bill_number = bill_text.replace("Bill ", "").strip()
#bill_number - H.3310

# Bill title
followable = heading.parent
follow_link = followable.find("a")
aria_label = follow_link.get("aria-label")
title = aria_label.replace("Follow in MyLegislature: ", "").strip()

print("Bill number:", bill_number)
print("Title:", title)

# description 
description_element = soup.find("p", class_="pinslip")
description = description_element.get_text(" ", strip=True)

print("Description:", description)

bill_info = soup.find("dl", class_="billInfo")

presenter_locate = bill_info.find("dt", string=lambda text: text and "Presenter:" in text)

presenter = presenter_locate.find_next_sibling("dd").get_text(" ", strip=True)

print("presenter:", presenter)

history_tab = soup.find("button", id="BillHistory-tab")

print("History tab:", history_tab)

history_url = "https://malegislature.gov" + history_tab.get("data-href")

history_response = requests.get(history_url, timeout=10)
history_response.raise_for_status()

history_soup = BeautifulSoup(history_response.text, "html.parser")

print(history_soup.get_text(" ", strip=True)[:3000])

import re
from io import BytesIO
from pypdf import PdfReader

# Download the bill PDF
pdf_url = "https://malegislature.gov/Bills/194/H3110.pdf"

pdf_response = requests.get(pdf_url, timeout=10)
pdf_response.raise_for_status()

# Read the PDF in memory
pdf_reader = PdfReader(BytesIO(pdf_response.content))

# Extract text from the first page
first_page_text = pdf_reader.pages[0].extract_text() or ""

print("First page of bill PDF:")
print(first_page_text[:2500])

# Locate the FILED ON label
filed_match = re.search(
    r"FILED\s+ON\s*:\s*([^\r\n]*)",
    first_page_text,
    re.IGNORECASE
)

if filed_match and filed_match.group(1).strip():
    filed_date_raw = filed_match.group(1).strip()
    filed_date = datetime.strptime(
        filed_date_raw, "%m/%d/%Y"
    ).date().isoformat()

    print("Filed date:", filed_date)
else:
    filed_date = None
    print("Filed date not found")

text_link = soup.find(
    "a",
    href=lambda href: href and href.endswith("/House/Bill/Text")
)

print("Text URL:", text_link["href"])

bill_text_url = "https://malegislature.gov" + text_link["href"]

text_response = requests.get(bill_text_url, timeout=10)
text_response.raise_for_status()

text_soup = BeautifulSoup(text_response.text, "html.parser")

print(text_soup.get_text(" ", strip=True)[-4000:])

for element in text_soup.find_all(string=lambda text: text and "SECTION 1." in text):
    print("Found in:", element.parent.name)
    print(element.parent.parent.prettify()[:4000])