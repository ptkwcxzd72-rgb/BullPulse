import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import departed as D  # noqa: E402


class DepartedTest(unittest.TestCase):
    def test_names(self):
        self.assertEqual(D.simple("Healthcare Services Group, Inc."), D.simple("HEALTHCARE SERVICES GROUP INC"))

    def test_prices_must_match_the_filings(self):
        quoted = {"2020-03-31": 10.0, "2020-06-30": 12.0, "2020-09-30": 24.0, "2020-12-31": 25.0}
        filed = {"2020-03-31": 10.1, "2020-06-30": 12.0, "2020-09-30": 12.0, "2020-12-31": 25.2}
        ok, _ = D.agrees(quoted, filed)          # September: a 2-for-1 split since, so the quote is half... or double
        self.assertTrue(ok)
        other = {"2020-03-31": 55.0, "2020-06-30": 40.0, "2020-09-30": 31.0, "2020-12-31": 70.0}
        self.assertFalse(D.agrees(other, filed)[0])   # a reused ticker: another company's prices

    def test_cover_page_symbol(self):
        page = '<tr><td class="pl"><a>Trading Symbol</a></td><td class="text">HCSG<span></span></td></tr>'
        self.assertEqual(D.symbol_on_cover(page), "HCSG")


if __name__ == "__main__":
    unittest.main()
