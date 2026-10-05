import requests
from bs4 import BeautifulSoup

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