"""Offline tests for isolated budget matching and unchanged bill matcher."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from budget_match import load_agenda_bills, load_budget, main, run_matching, split_budget_sections
from merge_match import match_pair
from budget_match_core import match_budget_pair, prepare_budget_target


ARGS = SimpleNamespace(
    lex_threshold=0.50,
    sem_threshold=0.80,
    concept_threshold=0.80,
    reworded_min_words=0.15,
    partial_threshold=0.70,
)

BILL_TEXT = (
    "SECTION 1. The department of education shall provide grants for after school "
    "programming to improve student attendance and academic outcomes across the commonwealth. "
    "SECTION 2. Every school district shall submit a written annual report to the "
    "department showing how grants were spent and reporting measurable outcomes."
)
BUDGET_TEXT = (
    "SECTION 2. Appropriations are provided for the following accounts.\n"
    "7009-1234 For public programs of the commonwealth, the department of education "
    "shall provide grants for after school programming to improve student attendance "
    "and academic outcomes across the commonwealth. Additional funds are available.\n"
    "7010-5678 For public libraries and community centers, with grants available for "
    "facility upgrades, improving access to books, and early literacy work.\n"
    "SECTION 3. The commissioner shall issue guidance for fiscal reports and oversight."
)


class TestBudgetMatching(unittest.TestCase):
    def test_budget_line_item_labels(self):
        units = split_budget_sections(BUDGET_TEXT)
        labels = [s for s, _ in units]
        self.assertTrue(any("7009-1234" in label for label in labels), labels)
        self.assertTrue(any("7010-5678" in label for label in labels), labels)

    def test_bill_to_bill_matcher_still_uses_original_global_matching(self):
        unchanged = match_pair(BILL_TEXT, BUDGET_TEXT, None, ARGS)
        budget_index = prepare_budget_target(BUDGET_TEXT, split_budget_sections(BUDGET_TEXT))
        budget = match_budget_pair(BILL_TEXT, budget_index, None, ARGS)
        self.assertNotIn("lexical_containment_global", unchanged[0])
        self.assertIn("lexical_containment_global", budget[0])

    def test_distant_passages_do_not_combine_into_false_verbatim(self):
        tokens = [f"uniqueword{i}" for i in range(40)]
        source = "SECTION 1. " + " ".join(tokens)
        target = (
            "SECTION 1. " + " ".join(tokens[:20]) +
            " SECTION 2. " + "unrelated words about roads and trees " * 8 +
            " SECTION 3. " + "unrelated words about parks and water " * 8 +
            " SECTION 4. " + " ".join(tokens[20:])
        )
        whole_budget = match_pair(source, target, None, ARGS)[0]
        index = prepare_budget_target(target, split_budget_sections(target))
        local_budget = match_budget_pair(source, index, None, ARGS)[0]
        self.assertEqual(whole_budget["match_type"], "verbatim")
        self.assertNotEqual(local_budget["match_type"], "verbatim")
        self.assertGreater(whole_budget["lexical_containment"], local_budget["lexical_containment"])

    def test_strong_match_and_passage_output(self):
        with tempfile.TemporaryDirectory() as d:
            bills_path = Path(d) / "bills.jsonl"
            with bills_path.open("w", encoding="utf-8") as out:
                out.write(json.dumps({"bill_number": "H.1", "title": "Test", "bill_text": BILL_TEXT}) + "\n")
                out.write(json.dumps({"bill_number": "S.2", "title": "Missing", "bill_text": ""}) + "\n")
            bills = load_agenda_bills(bills_path)
            scores, sections = run_matching(bills, BUDGET_TEXT, "budget-test", "fixture", None, ARGS)
            self.assertEqual(list(scores.status), ["ok", "missing bill text"])
            self.assertEqual(scores.iloc[0]["bill_number"], "H1")
            self.assertGreaterEqual(scores.iloc[0]["sections_strong_match"], 1)
            self.assertTrue(any("7009-1234" in str(v) for v in sections.best_target_section))
            self.assertTrue(all(sections.source_text.notna()))
            self.assertTrue(all(sections.target_text.notna()))
            self.assertEqual(scores.iloc[0]["budget_source"], "fixture")

    def test_local_text_budget(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "budget.txt"
            path.write_text(BUDGET_TEXT, encoding="utf-8")
            label, source, text = load_budget(path)
            self.assertEqual(label, "budget")
            self.assertEqual(source, str(path))
            self.assertEqual(text, BUDGET_TEXT)

    def test_cli_creates_both_csv_files(self):
        with tempfile.TemporaryDirectory() as d:
            bills_path = Path(d) / "bills.jsonl"
            budget_path = Path(d) / "budget.txt"
            out_dir = Path(d) / "output"
            bills_path.write_text(json.dumps({"bill_number": "H.1", "title": "Test", "bill_text": BILL_TEXT}) + "\n")
            budget_path.write_text(BUDGET_TEXT)
            main(["--bills", str(bills_path), "--budget", str(budget_path),
                  "--out", str(out_dir), "--no-embed"])
            self.assertTrue((out_dir / "budget_scores.csv").is_file())
            self.assertTrue((out_dir / "budget_sections.csv").is_file())
            self.assertIn("budget_source", (out_dir / "budget_scores.csv").read_text())

    def test_short_budget_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "budget.txt"
            path.write_text("", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "empty or too short"):
                load_budget(path)


if __name__ == "__main__":
    unittest.main()
