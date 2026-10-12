
# Progressive Massachusetts Legislature Tracker
 
Scrapes the bills on Progressive Massachusetts' legislative agenda from malegislature.gov: metadata, full text, filing date, and action history.

## Key Features

The scraper runs as a two-step pipeline: find the bills on the agenda, then scrape each one.

* `discover_agenda_bills.py` - builds the list of bills to scrape
  - Reads the [2025–2026 Progressive Mass legislative agenda](https://www.progressivemass.com/2025-2026-legislative-agenda/) and keeps every link that points to a malegislature.gov bill or docket (`H`, `S`, `HD`, `SD`).
  - Keeps one URL per bill ID and writes them to `agenda_bill_urls.csv`.
* `scrape_agenda.py` - scrapes every bill in the list
  - Reads `agenda_bill_urls.csv`, calls `scrape_bill()` on each URL, and writes one JSON record per bill to `output/agenda_bills.jsonl`.
  - Failures don't stop the run; they're logged to `output/agenda_errors.jsonl`.
  - Waits 1 second between bills to avoid hammering the legislature site.
* `scraper.py` - scraping logic for a single bill
  - `extract_bill_metadata()` gets the bill number, title, sponsor, and links to the text, PDF, and history pages.
  - `extract_filed_date()` reads the "FILED ON" date from the first page of the bill PDF.
  - `extract_bill_text()` pulls the bill text and drops the duplicate copy some pages show.
  - `extract_bill_history()` pulls each dated action from the bill history table.
  - Running it directly scrapes one test bill (HD3390) and saves it to `bill.json` (gitignored).
  - Docket numbers (e.g. `HD4328`) are never converted into guessed bill numbers. If a docket hasn't been assigned a bill number yet, the scraper uses the links on the docket page instead.
* `tests/test_scraper.py` - checks that the text of H.3110 comes back with sections 1–9 in order.

## How To Use

You'll need Python 3 and [Git](https://git-scm.com).

```bash
# Clone the repo and switch to this branch
git clone https://github.com/BU-Spark/ds-prog-mass-legislature.git
cd ds-prog-mass-legislature
git checkout feature/scraper

# Install dependencies (requests, beautifulsoup4, pypdf)
pip install -r requirements.txt

# Step 1: find the bills on the agenda -> agenda_bill_urls.csv
python discover_agenda_bills.py

# Step 2: scrape each bill -> output/agenda_bills.jsonl
python scrape_agenda.py

# Optional: scrape just the single test bill -> bill.json
python scraper.py

# Run the tests (needs internet access; hits the live site)
python -m unittest discover tests
```

A full run of step 2 takes a few minutes because of the 1-second delay plus three or four requests per bill.

For contributing: create a new branch from `dev`, open a Pull Request to `dev`, and add your PM and TPM as reviewers.

## Project Description

This is a BU Spark! DS539 (Fall 2026) project for Progressive Massachusetts. The goal is to track what happens to the bills on their legislative agenda as they move through the Massachusetts Legislature. This branch covers data collection: getting each agenda bill's details, text, and history into a structured format the rest of the project can build on.

## Data Locations

* `agenda_bill_urls.csv` - the agenda bill list (43 bills: 21 House dockets, 22 Senate dockets, all session 194)
  - Columns: `bill_id`, `session`, `link_text`, `url`
* `output/agenda_bills.jsonl` - scraped bills, one JSON object per line (43 records from the last run)
* `output/agenda_errors.jsonl` - URLs that failed, with `agenda_source_url`, `error_type`, `error` (empty after the last run)
* More detail: [Dataset Documentation](dataset-documentation)

Fields in each `agenda_bills.jsonl` record:

| Field | Description |
| :---- | :---- |
| `bill_number` | Assigned bill number, e.g. `H.3422`. Null if the docket hasn't been assigned one. |
| `title` | Bill title, e.g. "An Act establishing a jail and prison construction moratorium" |
| `description` | Intended to hold the "By Representative…" description. Currently always null (see Known Issues). |
| `presenter` | Lead sponsor |
| `bill_url` | URL that was scraped (usually the docket page) |
| `bill_page_url` | Official bill page |
| `bill_text_url` | Bill text page |
| `pdf_url` | Bill PDF |
| `history_url` | Bill history page |
| `filed_date` | Filing date from the PDF, ISO format (`YYYY-MM-DD`) |
| `bill_text` | Full bill text, one paragraph per line |
| `history` | List of actions, each with `date` (`M/D/YYYY`), `branch`, `action`, `related_bill` |
| `agenda_source_url` | The URL as it appeared in the agenda list |

## Known Issues

I found these while reading the code and the last run's output. They're worth fixing or at least knowing about before anyone uses the data.

* **`description` is null for all 43 bills.** The extractor looks for text like "By Representative…" inside the `billInfo` section, and it never matches. I couldn't check the live page from here, so the cause still needs confirming; most likely that text sits outside `dl.billInfo` or is worded differently.
* **HD4328 has no bill number and no history.** It hasn't been assigned a bill number, and its docket page has no link labeled "history", so `history_url` is null and `history` is empty. That's expected behavior for an unassigned docket, but it means one agenda bill has no tracking data.
* **Session 194 is hard-coded** when building bill URLs in `extract_bill_metadata()`. This will need updating for the next session.
* **A page without `dl.billInfo` will crash `extract_bill_metadata()`** with an `UnboundLocalError`, because the URL variables are only set inside that block. In the pipeline this gets logged as an error rather than stopping the run, but the bill is lost.
* **Date formats don't match.** `filed_date` is ISO (`2025-01-09`) while history dates are `M/D/YYYY` (`2/27/2025`).
* **The test depends on the live site**, so it fails offline or if the page changes.
* **`requirements.txt` has no version pins.**
