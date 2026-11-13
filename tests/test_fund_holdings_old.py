import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import fund_holdings_old as O  # noqa: E402

NEW = ("Schedule of Investments (Unaudited) \n iShares ® Core S&P Mid-Cap ETF \n (Percentages shown are based on Net Assets) \n | \n | \n Security | \n | \n Shares | \n | \n | \n Value | \n | \n Common Stocks \n | \n | \n"
       " Aerospace & Defense — 1.0% | \n | \n Curtiss-Wright Corp. (a) \n | \n | \n | \n 1,233,306 | \n | \n | \n $ | \n 125,945,209 | \n | \n"
       " Esterline Technologies Corp. (a)(b) \n | \n | \n | \n 747,229 | \n | \n | \n | \n 90,750,962 | \n | \n | \n | \n 426,828,529 | \n | \n"
       "Schedule of Investments \n iSHARES ® S&P MID-CAP 400 GROWTH ETF \n | \n Other Co. \n | \n 5 | \n 6 | \n"
       "Schedule of Investments (continued) \n iSHARES ® S&P MIDCAP 400 INDEX\nFUND \n December 31, 2008 \n | \n B/E Aerospace\nInc. a \n | \n | \n | \n 1,458,760 | \n | \n | \n | \n 126,955,883 | \n | \n Total Common Stocks | 1 | 2 |")


class OldHoldingsTest(unittest.TestCase):
    def test_sections_and_rows(self):
        secs = O.sections(NEW, "ijh")
        self.assertEqual(len(secs), 2)
        rows = [r for s in secs for r in O.holdings(s)]
        self.assertEqual([r["name"] for r in rows], ["Curtiss-Wright Corp.", "Esterline Technologies Corp.", "B/E Aerospace Inc."])
        self.assertEqual(rows[0]["shares"], 1233306)
        self.assertEqual(rows[1]["value_usd"], 90750962)

    def test_period(self):
        self.assertEqual(O.period_of("2019-03-01"), "2018-12-31")
        self.assertEqual(O.period_of("2018-08-29"), "2018-06-30")
        self.assertEqual(O.period_of("2019-06-07"), "2019-03-31")


if __name__ == "__main__":
    unittest.main()
