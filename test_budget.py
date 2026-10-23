import requests
from bs4 import BeautifulSoup
from io import BytesIO
from pypdf import PdfReader

pdf_url = "https://malegislature.gov/Bills/194/H2.pdf"
response = requests.get(pdf_url, timeout=120)
response.raise_for_status()

reader = PdfReader(BytesIO(response.content))
budget_text = " ".join(page.extract_text() or "" for page in reader.pages)

print("Number of pages:", len(reader.pages))
print("Number of characters:", len(budget_text))

with open("FY27_budget_text.txt", "w", encoding="utf-8") as f:
    f.write(budget_text)

print("Budget text saved!")