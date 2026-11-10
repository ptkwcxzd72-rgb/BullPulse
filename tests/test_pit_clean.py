import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from pit_clean import clean_shares  # noqa: E402


def rows(*shares, split=1):
    return [{"id": "X", "date": f"202{k}-05-01", "fin": {"shares": s}, "split": split} for k, s in enumerate(shares)]


class CleanSharesTest(unittest.TestCase):
    def test_spike_in_thousands_is_rescaled(self):
        r = rows(1e9, 1e12, 1.01e9)  # one filing stated in thousands as units
        clean_shares(r, price=lambda d: 50.0, market="US", index="S&P 500")
        self.assertAlmostEqual(r[1]["fin"]["shares"], 1e9)

    def test_newest_filings_wrong_uses_a_plausible_anchor(self):
        # 3i: the two newest UK reports gave 9.7m shares instead of 970m (prices in pence)
        r = rows(9.67e8, 9.68e6, 9.83e6)
        notes = clean_shares(r, price=lambda d: 2500.0, market="UK", per_unit=0.01, index="FTSE 100")
        self.assertEqual([round(x["fin"]["shares"] / 1e8, 1) for x in r], [9.7, 9.7, 9.8])
        self.assertEqual(len(notes), 2)

    def test_every_filing_wrong_by_the_same_factor(self):
        # Games Workshop: all three reports 100x too small
        r = rows(3.3e5, 3.3e5, 3.3e5)
        clean_shares(r, price=lambda d: 12000.0, market="UK", per_unit=0.01, index="FTSE 100")
        self.assertTrue(all(abs(x["fin"]["shares"] - 3.3e7) < 1 for x in r))

    def test_real_changes_are_left_alone(self):
        r = rows(1e9, 1.7e9, 2e8)  # a merger (x1.7) and a 1-for-5 reverse split stay as filed
        before = [x["fin"]["shares"] for x in r]
        self.assertEqual(clean_shares(r, price=lambda d: 40.0, market="US"), [])
        self.assertEqual([x["fin"]["shares"] for x in r], before)

    def test_unit_error_years_ago_after_buybacks(self):
        # Assurant: 118m shares in 2009 (one filing in thousands), 51m today; 2300x isn't a clean
        # power of ten from today's level, but 1000x is from the neighbouring filings
        r = rows(1.18e8, 1.18e11, 1.15e8, 8e7, 5.1e7)
        clean_shares(r, price=lambda d: 150.0, market="US", index="S&P 500")
        self.assertAlmostEqual(r[1]["fin"]["shares"], 1.18e8)
        self.assertAlmostEqual(r[0]["fin"]["shares"], 1.18e8)

    def test_years_of_filings_in_the_wrong_unit(self):
        # CenterPoint: early filings 1000x too large, the count since then up 50%
        r = rows(4.3e11, 4.3e11, 4.3e8, 5.5e8, 6.5e8)
        clean_shares(r, price=lambda d: 30.0, market="US", index="S&P 500")
        self.assertEqual([round(x["fin"]["shares"] / 1e8, 1) for x in r], [4.3, 4.3, 4.3, 5.5, 6.5])

    def test_bad_filing_doesnt_mislead_the_next(self):
        r = rows(1e9, 3.0, 1.02e9, 1.05e9)
        clean_shares(r, price=lambda d: 50.0, market="US", index="S&P 500")
        self.assertEqual(r[0]["fin"]["shares"], 1e9)
        self.assertNotIn("shares", r[1]["fin"])

    def test_impossible_value_is_dropped(self):
        r = rows(1e9, 3.0)  # a share count that can't be rescaled to anything sensible
        clean_shares(r, price=lambda d: 50.0, market="US", index="S&P 500")
        self.assertNotIn("shares", r[1]["fin"])


if __name__ == "__main__":
    unittest.main()
