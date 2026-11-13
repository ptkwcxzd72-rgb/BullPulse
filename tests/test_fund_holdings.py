import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import fund_holdings as H  # noqa: E402
import build_membership as BM  # noqa: E402

XML = b"""<?xml version="1.0"?>
<edgarSubmission xmlns="http://www.sec.gov/edgar/nport"><formData>
<genInfo><seriesName>iShares Core S&amp;P Mid-Cap ETF</seriesName><repPdDate>2025-03-31</repPdDate></genInfo>
<invstOrSecs>
<invstOrSec><name>Acme Corp</name><cusip>000000AA1</cusip><identifiers><isin value="US000000AA10"/><other otherDesc="Ticker" value="ACME"/></identifiers>
<balance>1000</balance><valUSD>50000</valUSD><pctVal>0.5</pctVal><assetCat>EC</assetCat></invstOrSec>
<invstOrSec><name>Cash fund</name><cusip>000000BB2</cusip><balance>1</balance><valUSD>1</valUSD><assetCat>STIV</assetCat></invstOrSec>
</invstOrSecs></formData></edgarSubmission>"""


class FundHoldingsTest(unittest.TestCase):
    def test_parse(self):
        series, period, rows = H.parse_nport(XML)
        self.assertEqual(series, "iShares Core S&P Mid-Cap ETF")
        self.assertEqual(period, "2025-03-31")
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["ticker"], rows[0]["isin"], rows[0]["value_usd"]), ("ACME", "US000000AA10", "50000"))


    def test_intervals(self):
        snaps = [("2020-03-31", {"A", "B"}), ("2020-06-30", {"A"}), ("2020-09-30", {"A", "B", "C"})]
        self.assertEqual(BM.intervals(snaps), [("A", "2020-03-31", ""), ("B", "2020-03-31", "2020-06-30"), ("B", "2020-09-30", ""), ("C", "2020-09-30", "")])
        gap = [("2014-09-30", {"A"}), ("2019-09-30", {"A"})]
        self.assertEqual(BM.intervals(gap), [("A", "2014-09-30", "2014-10-01"), ("A", "2019-09-30", "")])


if __name__ == "__main__":
    unittest.main()
