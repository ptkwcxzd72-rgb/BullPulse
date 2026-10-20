"""Unit tests for the Python data scripts (no network, no FinBERT). Run: python -m unittest discover tests"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import fetch_fundamentals as F  # noqa: E402
import fetch_news as N  # noqa: E402
import score_news as S  # noqa: E402
import sec_financials as SF  # noqa: E402
import fetch_uk_fundamentals as UKF  # noqa: E402
import sync_uk_prices as UKP  # noqa: E402
import fetch_insiders as INS  # noqa: E402


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


class Financials(unittest.TestCase):
    def facts(self):
        g = {
            "Revenues": {"units": {"USD": [fact("2023-01-01", "2023-12-31", 100), fact("2024-01-01", "2024-12-31", 110),
                                           fact("2025-01-01", "2025-12-31", 120), fact("2025-01-01", "2025-06-30", 55),
                                           fact("2026-01-01", "2026-06-30", 70), fact("2022-01-01", "2022-12-31", 90)]}},
            "NetIncomeLoss": {"units": {"USD": [fact("2023-01-01", "2023-12-31", 8), fact("2024-01-01", "2024-12-31", 10),
                                                fact("2025-01-01", "2025-12-31", 12)]}},
            "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [
                fact("2023-01-01", "2023-12-31", 15), fact("2024-01-01", "2024-12-31", 18), fact("2025-01-01", "2025-12-31", 21)]}},
            "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": [
                fact("2023-01-01", "2023-12-31", 5), fact("2024-01-01", "2024-12-31", 6), fact("2025-01-01", "2025-12-31", 7)]}},
            "StockholdersEquity": {"units": {"USD": [{"end": "2025-12-31", "val": 50}, {"end": "2026-06-30", "val": 55}]}},
            "LongTermDebtNoncurrent": {"units": {"USD": [{"end": "2026-06-30", "val": 25}]}},
            "LongTermDebtCurrent": {"units": {"USD": [{"end": "2026-06-30", "val": 5}]}},
        }
        return {"facts": {"us-gaap": g, "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [{"end": "2026-07-20", "val": 10}]}}}}}

    def test_ttm_from_year_to_date(self):
        f = SF.financials(self.facts())
        self.assertEqual(f["revenue_ttm"], 135)          # 120 + 70 - 55
        self.assertEqual(f["ttm_end"], "2026-06-30")

    def test_balance_and_cash_flow(self):
        f = SF.financials(self.facts())
        self.assertEqual(f["fcf_avg3"], 12)              # (10 + 12 + 14) / 3
        self.assertEqual(f["fcff_avg3"], 12)             # no share-based pay or interest in this sample
        self.assertEqual(f["debt"], 30)
        self.assertEqual(f["equity"], 55)
        self.assertEqual(f["shares"], 10)
        self.assertTrue(f["profitable_3y"])
        self.assertAlmostEqual(f["rev_cagr3"], (120 / 90) ** (1 / 3) - 1, places=4)
        self.assertGreater(f["net_margin_fy"], f["net_margin_prev_fy"])

    def test_ttm_columns_in_quarterly_reports_are_not_fiscal_years(self):
        def r(st, en, v, form):
            return {"start": st, "end": en, "val": v, "filed": "2026-01-01", "form": form}
        facts = {"facts": {"us-gaap": {"NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [
            r("2023-01-01", "2023-12-31", 10, "10-K"), r("2024-01-01", "2024-12-31", 20, "10-K"), r("2025-01-01", "2025-12-31", 30, "10-K"),
            r("2025-07-01", "2026-06-30", -50, "10-Q"), r("2025-04-01", "2026-03-31", -40, "10-Q")]}}}}}
        f = SF.financials(facts)
        self.assertEqual(f["fcf_avg3"], 20)              # fiscal years only
        self.assertEqual(f["ocf_ttm"], -50)              # the trailing twelve months still use the latest period

    def test_fcff_subtracts_share_based_pay_and_adds_back_interest(self):
        g = self.facts()["facts"]
        g["us-gaap"]["ShareBasedCompensation"] = {"units": {"USD": [fact("2023-01-01", "2023-12-31", 3), fact("2024-01-01", "2024-12-31", 3), fact("2025-01-01", "2025-12-31", 3)]}}
        g["us-gaap"]["InterestExpense"] = {"units": {"USD": [fact("2023-01-01", "2023-12-31", 1), fact("2024-01-01", "2024-12-31", 1), fact("2025-01-01", "2025-12-31", 1)]}}
        f = SF.financials({"facts": g})
        self.assertAlmostEqual(f["fcff_avg3"], 12 - 3 + 0.79, places=0)
        self.assertEqual(f["sbc_avg3"], 3)

    def test_empty(self):
        self.assertEqual(SF.financials({"facts": {}}), {})


class UK(unittest.TestCase):
    def xj(self, year, rev, ni):
        a, b = f"{year}-01-01T00:00:00", f"{year + 1}-01-01T00:00:00"
        def fact(c, v, unit="iso4217:USD", per=f"{a}/{b}", **extra):
            return {"value": str(v), "dimensions": {"concept": "ifrs-full:" + c, "entity": "lei:X", "period": per, "unit": unit, **extra}}
        return {"facts": {
            "r": fact("Revenue", rev), "n": fact("ProfitLossAttributableToOwnersOfParent", ni),
            "seg": fact("Revenue", 1, **{"ifrs-full:SegmentsAxis": "x"}),     # dimensioned: ignored
            "e": fact("DilutedEarningsLossPerShare", ni / 10, unit="iso4217:USD/xbrli:shares"),
            "o": fact("CashFlowsFromUsedInOperatingActivities", ni * 1.5), "c": fact("PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities", ni * .5),
            "b": fact("Borrowings", 40, per=b), "cb": fact("CurrentPortionOfNoncurrentBorrowings", 5, per=b),
            "q": fact("EquityAttributableToOwnersOfParent", 100, per=b), "sh": fact("AdjustedWeightedAverageShares", 10, unit="xbrli:shares")}}

    def test_extract_and_map(self):
        facts = UKF.extract(self.xj(2024, 200, 20))
        self.assertEqual(len([f for f in facts if f["c"] == "Revenue"]), 1)
        rev = [f for f in facts if f["c"] == "Revenue"][0]
        self.assertEqual((rev["s"], rev["e"]), ("2024-01-01", "2024-12-31"))
        filings = [("2025-03-01", facts), ("2024-03-01", UKF.extract(self.xj(2023, 160, 16))), ("2023-03-01", UKF.extract(self.xj(2022, 150, 12)))]
        cf, ccy = UKF.to_companyfacts(filings)
        self.assertEqual(ccy, "USD")
        fin = SF.financials(cf)
        self.assertEqual(fin["revenue_ttm"], 200)
        self.assertEqual(fin["debt"], 40)          # total borrowings: current part not added again
        self.assertEqual(fin["shares"], 10)
        self.assertTrue(fin["profitable_3y"])
        g = UKF.growth(cf)
        self.assertAlmostEqual(g["rev_growth"], 0.25)
        self.assertEqual(g["period"], "year")

    def test_yahoo_symbols_and_parse(self):
        self.assertEqual(UKP.yahoo_symbol("BT.A"), "BT-A.L")
        self.assertEqual(UKP.yahoo_symbol("RR."), "RR.L")
        d = {"chart": {"result": [{"meta": {"currency": "GBp"}, "timestamp": [1700000000, 1700086400],
             "indicators": {"quote": [{"open": [100, 102], "high": [103, 104], "low": [99, 101], "close": [101, 103], "volume": [5, 6]}],
                            "adjclose": [{"adjclose": [50.5, 103]}]}}]}}
        ccy, rows = UKP.parse_chart(d)
        self.assertEqual(ccy, "GBp")
        self.assertEqual(rows[0][4], 50.5)          # adjusted for the later dividend/split
        self.assertEqual(rows[0][1], 50.0)


FORM4 = b"""<?xml version="1.0"?><ownershipDocument>
<issuer><issuerCik>0000320193</issuerCik></issuer>
<reportingOwner><reportingOwnerId><rptOwnerName>DOE JANE</rptOwnerName></reportingOwnerId>
<reportingOwnerRelationship><isDirector>1</isDirector><isOfficer>0</isOfficer></reportingOwnerRelationship></reportingOwner>
<nonDerivativeTable>
<nonDerivativeTransaction><transactionDate><value>2026-09-01</value></transactionDate><transactionCoding><transactionCode>P</transactionCode></transactionCoding>
<transactionAmounts><transactionShares><value>1000</value></transactionShares><transactionPricePerShare><value>20.5</value></transactionPricePerShare></transactionAmounts></nonDerivativeTransaction>
<nonDerivativeTransaction><transactionDate><value>2026-09-02</value></transactionDate><transactionCoding><transactionCode>M</transactionCode></transactionCoding>
<transactionAmounts><transactionShares><value>50</value></transactionShares><transactionPricePerShare><value>1</value></transactionPricePerShare></transactionAmounts></nonDerivativeTransaction>
</nonDerivativeTable></ownershipDocument>"""


class Insiders(unittest.TestCase):
    def test_parse_purchase_only(self):
        tx = INS.parse_form4(FORM4, "320193")
        self.assertEqual(len(tx), 1)
        self.assertEqual((tx[0]["code"], tx[0]["val"], tx[0]["who"], tx[0]["role"]), ("P", 20500, "Doe Jane", "Director"))
        self.assertEqual(INS.parse_form4(FORM4, "999"), [])     # not this issuer

    def test_cluster(self):
        import datetime as dt
        txs = [{"d": "2026-09-01", "code": "P", "who": "A", "val": 10}, {"d": "2026-09-05", "code": "P", "who": "B", "val": 5},
               {"d": "2025-01-01", "code": "P", "who": "C", "val": 5}, {"d": "2026-09-03", "code": "S", "who": "A", "val": 99}]
        s = INS.summarise(txs, dt.date(2026, 10, 20))
        self.assertTrue(s["cluster"])
        self.assertEqual((s["buyers"], s["buyVal"], s["sellVal"]), (2, 15, 99))


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
