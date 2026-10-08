
import unittest

from scraper import extract_bill_text


class TestBillTextExtraction(unittest.TestCase):
    def test_bill_text_has_nine_sections(self):
        url = (
            "https://malegislature.gov/Bills/194/"
            "H3110/House/Bill/Text"
        )

        text = extract_bill_text(url)

        self.assertIsNotNone(text)

        import re
        sections = re.findall(r"\bSECTION\s+(\d+)\.", text)

        self.assertEqual(
            sections,
            ["1", "2", "3", "4", "5", "6", "7", "8", "9"],
        )


if __name__ == "__main__":
    unittest.main()