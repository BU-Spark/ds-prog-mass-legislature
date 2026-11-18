
# Progressive Massachusetts Legislature Tracker
 
Scrapes the bills on Progressive Massachusetts' legislative agenda from malegislature.gov: metadata, full text, filing date, and action history. Discovering relationship between legislative bills 

## Key Features

The scraper runs as a three-step pipeline: inding the agenda bills, scraping seed details, and crawling related legislation

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
* `crawl_related_bills.py` - recursive relationship crawler
  - Input into `output/agenda_bills.jsonl` as seed records.
  - Scans action logs for companion bills, or accompanied actions  (e.g., `H3591, H5311, S2696`).
  - Recursively fetches related bills up to `--max-bills` default  of 500
  - Generates a bill-to-bill graph edge list in `output/bill_relationships.csv`, complete record details in `output/all_bills.jsonl` and crawler run diagnostics into
    `output/related_bill_crawl_report.json`
* `export_actions.py` - flattens bill histories into a CSV tracker (`output/legislative_actions.csv`) any unassigned dockets lacking history are placed into
   `output/legislative_actions_review.json`
* `tests/test_scraper.py` - checks that the text of H.3110 comes back with sections 1–9 in order.
* `merge_match.py` - Compares bills with legislation they may have been merged into.
  - Measures wording overlap using five-word sequences.
  - Calculates semantic similarity between bill sections.
  - Compares shared concepts such as citations, dollar amounts, and defined terms.
  - Outputs bill-level and section-level matching scores.
* `refetch_bill_text.py` - Re-scrapes bill text to address incomplete or truncated records.
  - Retrieves updated bill text.
  - Compares old and new text lengths.
  - Generates a report of the results.

## How To Use

You'll need Python 3 and [Git](https://git-scm.com).

```bash
# Clone the repo and switch to this branch
git clone https://github.com/BU-Spark/ds-prog-mass-legislature.git
cd ds-prog-mass-legislature
git checkout dev

# Install dependencies (requests, beautifulsoup4, pypdf)
pip install -r requirements.txt

# Step 1: find the bills on the agenda -> agenda_bill_urls.csv
python discover_agenda_bills.py

# Step 2: scrape each bill -> output/agenda_bills.jsonl
python scrape_agenda.py

# Step 3: Crawl companion and referenced bills -> output/all_bills.jsonl & output/bill_relationships.csv
python crawl_related_bills.py --max-bills 500

# Step 4: Export denormalized actions -> output/legislative_actions.csv
python export_actions.py

# Step 5 (Optional): Re-fetch bill text to correct incomplete records
python refetch_bill_text.py --only-short

# Step 6: Compare merged bills using wording, meaning, and shared concepts
pip install pandas sentence-transformers
python merge_match.py

# Step 7: Compare agenda bills against the Massachusetts state budget
python budget_match.py

# Run the automated budget matching tests
python -m pytest -q

# Optional: Test matching on the first 5 pairs
python merge_match.py --limit 5

# Optional: Run matching without semantic embeddings
python merge_match.py --no-embed

# Optional: scrape just the single test bill -> bill.json
python scraper.py

# Run the tests (needs internet access; hits the live site)
python -m unittest discover -s tests
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
* `output/all_bills.jsonl` - combined dataset containing seed bills plus all recursively crawled related bills.
* `output/bill_relationships.csv` - directed relationship edge list mapping source bills to referenced legislation.
  - Columns: `source_bil`, `related_bill`, `relationship_type`, `action_date`, `branch`, `action`, `source_url`   
* output/`legislative_actions.csv` - action-level tabular dataset where each row corresponds to one event in a bill's history.
  - Columns: `Date`, `Branch`, `Bill Name`, `Bill Number`, `Bill Content`, `Stage`, `Action`, `Related Bill`, `Sources`
* Sourcesoutput/legislative_actions_review.json - data quality audit file logging bills/dockets with missing histories.
* output/related_bill_crawl_report.json - crawler diagnostics (coverage counts, unresolved references, error logs)
* output/merge_scores.csv - Bill-level matching scores and incorporation estimates.
* output/merge_sections.csv - Section-level comparisons based on wording, semantic similarity, and shared concepts.
* output/study_orders.csv - Bills identified as sent to study orders.
* output/all_bills.before_refetch.jsonl - backup of the original bill dataset before re-fetching bill text.
* output/refetch_report.csv - report comparing the original and updated bill text lengths after re-fetching.
* output/retry_failed_bills_report.json - results of retrying bills that previously failed during crawling.
* output/missing_refs_recovery_report.json - results of attempts to recover missing referenced bills.
* `output/budget_scores.csv` - Bill-level budget matching results, including the best matching budget passage, semantic similarity score, shared policy terms, policy evidence, and statutory reference overlap.
* [Massachusetts Budget H5555](https://malegislature.gov/Bills/194/H5555.pdf) - Budget document used for matching.
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

Fields in each `legislative_actions.csv` record:

| Field | Description |
| :---- | :---- |
| `Date` | Date action took place (`M/D/YYYY`) |
| `Branch` | Chamber taking action (`House`, `Senate`, or `Joint` |
| `Bill Name` | Bill title, e.g. "An Act establishing a jail and prison construction moratorium" |
| `Bill Number` | Assigned bill number, e.g. `H.3422` or `S.1127`. Null if the docket hasn't been assigned one.|
| `Bill Content` | Web link pointing to the official bill page|
| `Stage` |  Classification category of the bill's current standing (`Referred`, `Hearing`, `Extension`, `Concurred`, `Accompanied`) |
| `Action` | Full raw text description of the recorded action |
| `Related Bill` | Referenced companion bills, study orders, or new drafts|
| `Source` |Legislative history page link|


## Known Issues

I found these while reading the code and the last run's output. They're worth fixing or at least knowing about before anyone uses the data.

* **`description` is null for all 43 bills.** The extractor looks for text like "By Representative…" inside the `billInfo` section, and it never matches. I couldn't check the live page from here, so the cause still needs confirming; most likely that text sits outside `dl.billInfo` or is worded differently.
* **HD4328 has no bill number and no history.** It hasn't been assigned a bill number, and its docket page has no link labeled "history", so `history_url` is null and `history` is empty. That's expected behavior for an unassigned docket, but it means one agenda bill has no tracking data.
* **Session 194 is hard-coded** when building bill URLs in `extract_bill_metadata()`. This will need updating for the next session.
* **A page without `dl.billInfo` will crash `extract_bill_metadata()`** with an `UnboundLocalError`, because the URL variables are only set inside that block. In the pipeline this gets logged as an error rather than stopping the run, but the bill is lost.
* **Date formats don't match.** `filed_date` is ISO (`2025-01-09`) while history dates are `M/D/YYYY` (`2/27/2025`).
* **The test depends on the live site**, so it fails offline or if the page changes.
* **`requirements.txt` has no version pins.**

