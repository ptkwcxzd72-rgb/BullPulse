import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import build_membership as BM  # noqa: E402
import smid_check as C  # noqa: E402


class SmidCheckTest(unittest.TestCase):
    def test_copy_tracks_its_fund(self):
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "ijh"))
        open(os.path.join(d, "ijh", "2020-03-31.csv"), "w").write("name,cusip,isin,ticker,shares,value_usd,pct\nA,1,,A,1,300,60\nB,2,,B,1,200,40\n")
        mem = os.path.join(d, "m.csv")
        open(mem, "w").write("ticker,start_date,end_date\nA,2020-03-31,\nB,2020-03-31,\n")
        old = (BM.SRC, C.FUNDS)
        BM.SRC, C.FUNDS = d, {"S&P 400": ("ijh", "IJH", mem)}
        try:
            ends = C.month_ends("2020-03-01", "2021-12-31")
            ra, rb = 0.02, -0.01   # monthly returns
            A = (ends, [100 * (1 + ra) ** k for k in range(len(ends))])
            B = (ends, [50 * (1 + rb) ** k for k in range(len(ends))])
            # the fund: value-weighted with weights drifting with the returns
            fv = [300 * (1 + ra) ** k + 200 * (1 + rb) ** k for k in range(len(ends))]
            r = C.check("S&P 400", {"A": A, "B": B}.get, fund=(ends, fv))
        finally:
            BM.SRC, C.FUNDS = old
        self.assertLess(abs(r["gap"]), 1e-9)
        self.assertLess(r["te"], 1e-9)
        self.assertEqual(r["coverage_min"], 1.0)


if __name__ == "__main__":
    unittest.main()
