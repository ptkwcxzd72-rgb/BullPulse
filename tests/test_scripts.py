"""Unit tests for the Python data scripts (no network, no FinBERT). Run: python -m unittest discover tests"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import fetch_fundamentals as F  # noqa: E402
import fetch_news as N  # noqa: E402
import score_news as S  # noqa: E402


def fact(start, end, val, filed="2026-01-01"):
    return {"start": start, "end": end, "val": val, "filed": filed}


class Fundamentals(unittest.TestCase):
    def test_quarterly_growth_and_acceleration(self):
        facts = {"facts": {"us-gaap": {
            "Revenues": {"units": {"USD": [fact("2024-04-01", "2024-06-30", 95), fact("2024-07-01", "2024-09-30", 100),
                                           fact("2025-04-01", "2025-06-30", 110), fact("2025-07-01", "2025-09-30", 130)]}},
            "EarningsPerShareDiluted": {"units": {"USD/shares": [fact("2024-07-01", "2024-09-30", 1.0),
                                                                 fact("2025-07-01", "2025-09-30", 1.5)]}}}}}
        a = F.analyse(facts)
        self.assertEqual(a["period"], "quarter")
        self.assertAlmostEqual(a["rev_growth"], 0.30, places=4)
        self.assertGreater(a["rev_accel"], 0)
        self.assertAlmostEqual(a["eps_growth"], 0.5, places=4)

    def test_annual_fallback_and_later_filing_wins(self):
        facts = {"facts": {"us-gaap": {"SalesRevenueNet": {"units": {"USD": [
            fact("2023-01-01", "2023-12-31", 200), fact("2024-01-01", "2024-12-31", 170, "2025-02-01"),
            fact("2024-01-01", "2024-12-31", 180, "2025-03-01")]}}}}}
        a = F.analyse(facts)
        self.assertEqual(a["period"], "year")
        self.assertAlmostEqual(a["rev_growth"], -0.10, places=4)

    def test_no_data(self):
        self.assertIsNone(F.analyse({"facts": {}}))


class News(unittest.TestCase):
    def test_relevance(self):
        amzn = {"name": "Amazon.com Inc.", "ticker": "AMZN"}
        self.assertEqual(N.relevance("Amazon raises outlook", amzn, 1.0), 1.0)
        self.assertLess(N.relevance("Tech stocks fall on Friday", amzn, 1.0), 0.5)
        jpm = {"name": "JPMorgan Chase", "ticker": "JPM"}
        self.assertLess(N.relevance("JPMorgan sees 80% upside in Alibaba", jpm, 1.0), 0.5)
        self.assertEqual(N.relevance("JPMorgan beats on trading revenue", jpm, 1.0), 1.0)

    def test_syndication_key(self):
        self.assertEqual(N.norm_headline("Apple beats estimates — shares rise 3%!"),
                         N.norm_headline("Apple Beats Estimates; Shares Rise 3%"))

    def test_event_types(self):
        self.assertEqual(S.event_type("Acme Q3 results beat forecasts"), "Earnings")
        self.assertEqual(S.event_type("Acme agrees takeover by Rival"), "M&A")
        self.assertEqual(S.event_type("Acme chief executive steps down"), "Management")


if __name__ == "__main__":
    unittest.main()
