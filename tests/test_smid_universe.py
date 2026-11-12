import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import build_smid_universe as B  # noqa: E402

ROWS = "".join(f"<tr><td><a>T{k}</a></td><td><a>Company {k}</a>[1]</td><td>Industrials</td><td>Machinery</td></tr>" for k in range(150))
PAGE = f"""<html><table class="infobox"><tr><th>Founded</th><td>1991</td></tr></table>
<table class="wikitable sortable"><tr><th>Symbol</th><th>Security</th><th>GICS Sector</th><th>GICS Sub-Industry</th></tr>
<tr><td>BRK.B</td><td>Nested <table><tr><td>x</td></tr></table> Co</td><td>Financials</td><td>x</td></tr>{ROWS}</table></html>""".encode()


class SmidTest(unittest.TestCase):
    def test_constituent_table(self):
        rows = B.constituents(PAGE)
        self.assertEqual(len(rows), 151)
        self.assertEqual(rows[1], {"ticker": "T0", "name": "Company 0", "sector": "Industrials"})
        self.assertEqual(rows[0]["sector"], "Financials")


if __name__ == "__main__":
    unittest.main()
