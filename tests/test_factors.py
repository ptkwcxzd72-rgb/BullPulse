import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import fetch_factors as F  # noqa: E402

FIVE = """This file was created using the 202609 CRSP database.
The 1-month TBill return is from Ibbotson and Associates Inc.

,Mkt-RF,SMB,HML,RMW,CMA,RF
196307,   -0.39,   -0.48,   -0.81,    0.64,   -1.15,    0.27
196308,    5.07,   -0.80,    1.70,    0.40,   -0.38,    0.25

 Annual Factors: January-December
,Mkt-RF,SMB,HML,RMW,CMA,RF
  1964,   12.57,    0.07,    9.86,    2.69,    5.40,    3.54
"""
MOM = """Missing data are indicated by -99.99.

,Mom
196308,    1.01
196309,   -99.99

Annual Factors:
,Mom
1964,  12.0
"""


class FactorsTest(unittest.TestCase):
    def test_monthly_table_only(self):
        f = F.monthly(FIVE)
        self.assertEqual(sorted(f), ["1963-07", "1963-08"])
        self.assertAlmostEqual(f["1963-08"]["Mkt-RF"], 0.0507)

    def test_missing_values_and_join(self):
        out = F.build(F.monthly(FIVE), F.monthly(MOM))
        self.assertEqual(out["months"], ["1963-08"])     # momentum missing in July, -99.99 in September
        self.assertAlmostEqual(out["mom"][0], 0.0101)
        self.assertAlmostEqual(out["rf"][0], 0.0025)


if __name__ == "__main__":
    unittest.main()
