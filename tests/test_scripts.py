"""Unit tests for the Python data scripts (no network, no FinBERT). Run: python -m unittest discover tests"""
import os
import sys
import csv
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

    def test_assets_and_gross_profit(self):
        facts = self.facts()
        g = facts["facts"]["us-gaap"]
        g["Assets"] = {"units": {"USD": [{"end": "2025-06-30", "val": 400}, {"end": "2025-12-31", "val": 420},
                                         {"end": "2026-06-30", "val": 460}]}}
        g["CostOfRevenue"] = {"units": {"USD": [fact("2025-01-01", "2025-12-31", 70), fact("2025-01-01", "2025-06-30", 30),
                                                fact("2026-01-01", "2026-06-30", 40)]}}
        f = SF.financials(facts)
        self.assertEqual(f["assets"], 460)
        self.assertEqual(f["assets_prev"], 400)          # the balance sheet a year before the latest
        self.assertEqual(f["gross_profit_ttm"], 135 - 80)  # revenue less cost of sales, both trailing twelve months

    def test_beneish_m_score(self):
        y = lambda v1, v0: {"units": {"USD": [fact("2024-01-01", "2024-12-31", v0, "2025-02-01"), fact("2025-01-01", "2025-12-31", v1, "2026-02-01")]}}
        i = lambda v1, v0: {"units": {"USD": [{"end": "2024-12-31", "val": v0, "filed": "2025-02-01"}, {"end": "2025-12-31", "val": v1, "filed": "2026-02-01"}]}}
        g = {"Revenues": y(1200, 1000), "CostOfRevenue": y(720, 580), "NetIncomeLoss": y(100, 90),
             "NetCashProvidedByUsedInOperatingActivities": y(60, 95), "DepreciationDepletionAndAmortization": y(50, 50),
             "SellingGeneralAndAdministrativeExpense": y(180, 160), "AccountsReceivableNetCurrent": i(300, 200),
             "PropertyPlantAndEquipmentNet": i(500, 500), "Assets": i(2000, 1800), "AssetsCurrent": i(800, 700),
             "LiabilitiesCurrent": i(400, 350), "LongTermDebtNoncurrent": i(500, 400)}
        b = SF.beneish({"facts": {"us-gaap": g}}, SF.durations({"facts": {"us-gaap": g}}, SF.REVENUE))
        self.assertEqual(b["fy"], "2025-12-31")
        self.assertAlmostEqual(b["dsri"], (300 / 1200) / (200 / 1000), places=4)
        self.assertAlmostEqual(b["sgi"], 1.2, places=4)
        self.assertAlmostEqual(b["tata"], (100 - 60) / 2000, places=4)
        self.assertAlmostEqual(b["gmi"], (420 / 1000) / (480 / 1200), places=4)
        ix = {k: b[k] for k in ("dsri", "gmi", "aqi", "sgi", "depi", "sgai", "tata", "lvgi")}
        self.assertAlmostEqual(b["m"], -4.84 + sum(SF.BENEISH[k] * v for k, v in ix.items()), places=2)
        self.assertEqual(b["missing"], [])

    def test_beneish_needs_receivables(self):
        y = lambda v1, v0: {"units": {"USD": [fact("2024-01-01", "2024-12-31", v0), fact("2025-01-01", "2025-12-31", v1)]}}
        g = {"Revenues": y(1200, 1000), "NetIncomeLoss": y(100, 90), "NetCashProvidedByUsedInOperatingActivities": y(60, 95)}
        self.assertIsNone(SF.beneish({"facts": {"us-gaap": g}}, SF.durations({"facts": {"us-gaap": g}}, SF.REVENUE)))

    def test_share_count_a_year_earlier(self):
        facts = self.facts()
        facts["facts"]["dei"] = {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
            {"end": "2025-02-01", "val": 1000}, {"end": "2025-08-01", "val": 990}, {"end": "2026-02-03", "val": 950}]}}}
        f = SF.financials(facts)
        self.assertEqual(f["shares"], 950)
        self.assertEqual(f["shares_prev"], 1000)          # the cover-page count nearest a year before

    def test_ttm_columns_in_quarterly_reports_are_not_fiscal_years(self):
        def r(st, en, v, form):
            return {"start": st, "end": en, "val": v, "filed": "2026-01-01", "form": form}
        facts = {"facts": {"us-gaap": {"NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [
            r("2023-01-01", "2023-12-31", 10, "10-K"), r("2024-01-01", "2024-12-31", 20, "10-K"), r("2025-01-01", "2025-12-31", 30, "10-K"),
            r("2025-07-01", "2026-06-30", -50, "10-Q"), r("2025-04-01", "2026-03-31", -40, "10-Q")]}},
            "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": [
            r("2023-01-01", "2023-12-31", 0, "10-K"), r("2024-01-01", "2024-12-31", 0, "10-K"), r("2025-01-01", "2025-12-31", 0, "10-K")]}}}}}
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

    def test_unfinished_day(self):
        import datetime as dt
        self.assertEqual(UKP.unfinished_day(dt.datetime(2026, 10, 23, 11, 0)), "2026-10-23")
        self.assertEqual(UKP.unfinished_day(dt.datetime(2026, 10, 23, 22, 0)), "")

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
        self.assertEqual((tx[0]["code"], tx[0]["val"], tx[0]["who"], tx[0]["role"]), ("P", 20500, "Jane Doe", "Director"))
        self.assertEqual(INS.person_name("BERKSHIRE HATHAWAY INC"), "Berkshire Hathaway Inc")
        self.assertEqual(INS.person_name("Buckley Mortimer J"), "Mortimer J Buckley")
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


class NightlyGuardTest(unittest.TestCase):
    def test_duplicates_and_close(self):
        import datetime as dt
        import nightly_guard as g
        utc = dt.timezone.utc
        now = dt.datetime(2026, 10, 28, 22, 0, tzinfo=utc)
        quick = {"id": 1, "status": "completed", "conclusion": "success", "event": "workflow_dispatch",
                 "run_started_at": "2026-10-28T14:00:00Z", "updated_at": "2026-10-28T14:40:00Z"}
        skipped = {"id": 2, "status": "completed", "conclusion": "success", "event": "schedule",
                   "run_started_at": "2026-10-28T21:15:00Z", "updated_at": "2026-10-28T21:15:30Z"}
        self.assertEqual(g.duplicate([quick, skipped], now), "")
        real = {"id": 3, "status": "completed", "conclusion": "success", "event": "workflow_run",
                "run_started_at": "2026-10-28T20:00:00Z", "updated_at": "2026-10-29T00:30:00Z"}
        self.assertIn("run 3", g.duplicate([real], now))
        self.assertIn("in_progress", g.duplicate([{"id": 4, "status": "in_progress"}], now))
        self.assertAlmostEqual(g.wait_for_close(dt.datetime(2026, 10, 28, 19, 30, tzinfo=utc)), 40 * 60)
        self.assertEqual(g.wait_for_close(dt.datetime(2026, 10, 31, 12, 0, tzinfo=utc)), 0)  # Saturday


class InsiderHistoryTest(unittest.TestCase):
    def test_parse_bulk_tables(self):
        import io as _io
        import zipfile as _zf
        import insider_history as IH
        buf = _io.BytesIO()
        with _zf.ZipFile(buf, "w") as z:
            z.writestr("SUBMISSION.tsv", "ACCESSION_NUMBER\tFILING_DATE\tDOCUMENT_TYPE\tISSUERCIK\n"
                       "A1\t05-MAR-2024\t4\t0000320193\nA2\t06-MAR-2024\t4\t999\nA3\t07-MAR-2024\t3\t320193\n")
            z.writestr("REPORTINGOWNER.tsv", "ACCESSION_NUMBER\tRPTOWNERNAME\tRPTOWNER_RELATIONSHIP\tRPTOWNER_TITLE\n"
                       "A1\tCOOK TIMOTHY\tOFFICER\tCEO\n")
            z.writestr("NONDERIV_TRANS.tsv", "ACCESSION_NUMBER\tTRANS_DATE\tTRANS_CODE\tTRANS_SHARES\tTRANS_PRICEPERSHARE\n"
                       "A1\t01-MAR-2024\tP\t100\t170.5\nA1\t01-MAR-2024\tM\t100\t0\nA2\t01-MAR-2024\tP\t5\t1\n")
        rows = IH.parse(buf.getvalue(), {"320193": "US-AAPL"})
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r["filed"], r["trade"], r["id"], r["code"], r["value"], r["role"]),
                         ("2024-03-05", "2024-03-01", "US-AAPL", "P", 17050, "OFFICER"))
        self.assertEqual(IH.quarters("2025q3", __import__("datetime").date(2026, 2, 1)), ["2025q3", "2025q4", "2026q1"])


class DividendAdjustTest(unittest.TestCase):
    def test_total_return_back_adjustment(self):
        import sync_uk_prices as U
        bars = [["2024-01-01", 100, 100, 100, 100, 1], ["2024-01-02", 100, 100, 100, 100, 1], ["2024-01-03", 95, 95, 95, 95, 1]]
        out = U.add_dividends(bars, [["2024-01-03", 5.0]])
        # the price fell by the dividend: a holder's total return is zero
        self.assertAlmostEqual(out[2][4] / out[1][4], 1.0, places=6)
        self.assertEqual(out[2][4], 95)
        d = {"chart": {"result": [{"indicators": {"quote": [{"close": [100, 95]}], "adjclose": [{"adjclose": [100, 95]}]},
                                   "events": {"dividends": {"1": {"amount": 5, "date": 1704240000}}}}]}}
        self.assertTrue(U.dividends_missing(d))
        d["chart"]["result"][0]["indicators"]["adjclose"][0]["adjclose"] = [95, 95]
        self.assertFalse(U.dividends_missing(d))

    def test_several_dividends_use_quoted_closes(self):
        # two 10p dividends on a 100p share that doesn't move otherwise: each ex-date scales earlier
        # prices by 0.9, so the first price is 81, not less (older dividends must not be overstated)
        import sync_uk_prices as U
        bars = [["2024-01-0%d" % (k + 1), 100, 100, 100, p, 1] for k, p in enumerate([100, 90, 100, 90])]
        out = U.add_dividends(bars, [["2024-01-02", 10.0], ["2024-01-04", 10.0]])
        self.assertAlmostEqual(out[3][4], 90)
        self.assertAlmostEqual(out[2][4], 90)          # 100 x 0.9
        self.assertAlmostEqual(out[1][4], 90 * 0.9)    # 90 x 0.9
        self.assertAlmostEqual(out[0][4], 100 * 0.81)  # 100 x 0.9 x 0.9
        # returns: flat on both ex-dates for a holder who reinvests
        self.assertAlmostEqual(out[1][4] / out[0][4], 0.9 / 0.9 * 0.9 / 0.9 * 1.0, places=6)

    def test_partial_adjustment_is_missing(self):
        # Legal & General's case: Yahoo adjusted for one small event but not the regular dividends,
        # so adjusted closes differ from closes, yet most of the income is missing
        import sync_uk_prices as U
        n = 40
        ts = [1700000000 + 86400 * k for k in range(n)]
        close = [100.0] * n
        adj = [99.0] * 10 + [100.0] * 30           # a 1% adjustment early on only
        divs = {str(k): {"amount": 6.0, "date": ts[k]} for k in (10, 20, 30)}   # 3 x 6%: about 17%
        d = {"chart": {"result": [{"timestamp": ts, "indicators": {"quote": [{"close": close, "open": close, "high": close, "low": close, "volume": [1] * n}], "adjclose": [{"adjclose": adj}]},
                                   "events": {"dividends": divs}, "meta": {"currency": "GBp"}}]}}
        self.assertTrue(U.dividends_missing(d))
        _, bars = U.parse_chart(d, raw=True)
        self.assertEqual(bars[0][4], 100.0)         # raw closes, so the partial adjustment isn't counted twice
        # properly adjusted: the earliest close is scaled by the dividends (0.94^3)
        d["chart"]["result"][0]["indicators"]["adjclose"][0]["adjclose"] = [100 * 0.94 ** sum(1 for j in (10, 20, 30) if j > k) for k in range(n)]
        self.assertFalse(U.dividends_missing(d))


class USYahooTest(unittest.TestCase):
    def test_coverage_and_unfinished_day(self):
        import datetime as dt
        from zoneinfo import ZoneInfo
        import sync_us_yahoo as Y
        t = Y.tiingo_tickers()
        self.assertEqual(len(t), 210)                      # what sync_prices.sh downloads on the free tier
        old = {k: os.environ.get(k) for k in ("MAX_TICKERS", "TIINGO_TIER")}
        try:
            os.environ["MAX_TICKERS"], os.environ["TIINGO_TIER"] = "", "free"   # as the workflow passes unset variables
            self.assertEqual(len(Y.tiingo_tickers()), 210)
        finally:
            for k, v in old.items():
                os.environ.pop(k, None)
                if v is not None:
                    os.environ[k] = v
        rows = list(csv.DictReader(open("universe/us.csv", newline="")))
        rest = {r["provider_ticker"] for r in rows} - t
        self.assertIn("msft", rest)                       # the rest of the index comes from Yahoo
        self.assertEqual(len(rest) + len(t & {r["provider_ticker"] for r in rows}), len({r["provider_ticker"] for r in rows}))
        ny = ZoneInfo("America/New_York")
        self.assertEqual(Y.ny_unfinished_day(dt.datetime(2026, 11, 6, 15, 0, tzinfo=ny)), "2026-11-06")
        self.assertEqual(Y.ny_unfinished_day(dt.datetime(2026, 11, 6, 17, 0, tzinfo=ny)), "")
        self.assertEqual(Y.yahoo_symbol("BRK.B"), "BRK-B")


class SplitRatioTest(unittest.TestCase):
    def test_reverse_splits(self):
        import fundamentals_history as F
        self.assertEqual(F.split_ratio(8.7e9, 8.7e9 / 8 * 1.02), 1 / 8)   # GE, 2021
        self.assertEqual(F.split_ratio(1e9, 2e9), 2)
        self.assertEqual(F.split_ratio(1e9, 1.05e9), 1.0)                 # issuance, not a split
        self.assertEqual(F.split_ratio(1e9, 0.9e9), 1.0)                  # buyback, not a split


class ThirteenFTest(unittest.TestCase):
    def test_parse_and_aggregate(self):
        import fetch_13f as F
        xml = b"""<?xml version="1.0"?><informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
        <infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>037833100</cusip><value>1000</value>
        <shrsOrPrnAmt><sshPrnamt>10</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
        <infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>COM</titleOfClass><cusip>037833100</cusip><value>500</value>
        <shrsOrPrnAmt><sshPrnamt>5</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
        <infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><titleOfClass>CALL</titleOfClass><cusip>037833100</cusip><value>99</value><putCall>Call</putCall>
        <shrsOrPrnAmt><sshPrnamt>1</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable></informationTable>"""
        rows = F.parse_table(xml)
        self.assertEqual(len(rows), 2)
        agg = F.aggregate(rows, "2024-05-01")   # $100 a share: values are dollars
        self.assertEqual((agg[0]["value"], agg[0]["shares"]), (1500.0, 15.0))
        thou = [dict(r, shares=r["shares"] * 1000) for r in rows]   # $0.10 a share: values are thousands
        self.assertEqual(F.aggregate(thou, "2024-05-01")[0]["value"], 1500000.0)
        self.assertEqual(F.norm("COCA COLA CO"), "COCA COLA")

    def test_changes_and_copy_record(self):
        import investors as I
        prev = [{"cusip": "A", "name": "A", "value": 50, "shares": 10}, {"cusip": "B", "name": "B", "value": 50, "shares": 10}]
        cur = [{"cusip": "A", "name": "A", "value": 80, "shares": 20}, {"cusip": "C", "name": "C", "value": 20, "shares": 5}]
        c = I.changes(prev, cur)
        self.assertEqual([h["cusip"] for h in c["new"]], ["C"])
        self.assertEqual([h["cusip"] for h in c["added"]], ["A"])
        self.assertEqual([h["cusip"] for h in c["sold"]], ["B"])
        days = ["2024-01-02", "2024-01-03", "2024-01-31", "2024-02-01", "2024-02-29", "2024-03-01"]
        px = {"AAA": (days, [10, 10, 11, 11, 12, 12])}
        bench = (days, [100, 100, 100, 100, 100, 100])
        doc = {"filings": [{"filed": "2024-01-02", "holdings": [{"ticker": "AAA", "value": 1, "cusip": "X"}, {"ticker": "", "value": 1, "cusip": "Y"}]}]}
        r = I.copy_record(doc, px, bench)
        self.assertAlmostEqual(r["total"], 0.2, places=6)   # 10 -> 12, bought on the first close after filing
        self.assertAlmostEqual(r["coverage"], 0.5)
        self.assertEqual(I.month_ends("2024-01-03", "2024-03-01"), ["2024-01-31", "2024-02-29"])
    def test_name_match(self):
        import fetch_13f as F
        sec = {F.norm("Janus Henderson Group plc"): "JHG", F.norm("Ferguson Enterprises Inc."): "FERG",
               F.norm("Bank of America Corp"): "BAC", F.norm("Bank of Hawaii Corp"): "BOH"}
        self.assertEqual(F.match_name("Janus Henderson Group plc", {}, sec), "JHG")    # exact, after dropping 'Group plc'
        self.assertEqual(F.match_name("Ferguson Plc New", {}, sec), "FERG")            # the only name it begins
        self.assertEqual(F.match_name("BANK OF", {}, sec), "")                         # ambiguous: no match
        self.assertEqual(F.match_name("Janus Henderson Group plc", {F.norm("Janus Henderson"): "XYZ"}, sec), "XYZ")  # universe first

    def test_news_feed(self):
        import news_feed as N
        ids = {("US", "AAA"): "US-AAA", ("US", "BBB"): "US-BBB"}
        rows = [
            {"date": "2026-11-02", "ticker": "AAA", "market": "US", "headline": "Big news for AAA and BBB", "source": "X", "url": "u1", "rel": 1.0, "score": 0.9, "label": "Positive", "event": "Earnings"},
            {"date": "2026-11-02", "ticker": "BBB", "market": "US", "headline": "Big news for AAA and BBB!", "source": "X", "url": "u1", "rel": 0.3, "score": 0.9, "label": "Positive", "event": "Other"},
            {"date": "2026-11-02", "ticker": "AAA", "market": "US", "headline": "AAA again", "source": "Y", "url": "u2", "rel": 1.0, "score": -0.5, "label": "Negative", "event": "Earnings"},
            {"date": "2026-11-02", "ticker": "BBB", "market": "US", "headline": "BBB story", "source": "Y", "url": "u3", "rel": 1.0, "score": 0.1, "label": "Neutral", "event": "Other"},
            {"date": "2026-11-02", "ticker": "CCC", "market": "US", "headline": "Unscored", "source": "Y", "url": "u4", "rel": 1.0, "score": None}]
        d = N.build(rows, ids)["2026-11-02"]
        self.assertEqual(len(d), 3)                                   # the same story once; unscored left out
        first = d[0]
        self.assertEqual((first["about"], first["also"], first["ev"]), (["US-AAA"], ["US-BBB"], "Earnings"))
        self.assertEqual(d[1]["about"], ["US-BBB"])                   # another company before AAA's second story
        s = N.summary("2026-11-02", d, {})
        self.assertEqual((s["n"], s["pos"], s["neg"], s["top"][0]["id"]), (3, 1, 1, "US-AAA"))

    def test_stakes(self):
        import fetch_13f as F
        import investors as I
        hdr = b"""<html><pre>&lt;SEC-HEADER&gt;\nSUBJECT COMPANY:\n\n\tCOMPANY DATA:\t\n\t\tCOMPANY CONFORMED NAME:\t\t\tWENDY'S CO\n\t\tCENTRAL INDEX KEY:\t\t\t0000030697\n\nFILED BY:\n\n\tCOMPANY DATA:\n\t\tCOMPANY CONFORMED NAME:\t\t\tTrian Fund Management, L.P.\n\t\tCENTRAL INDEX KEY:\t\t\t0001345471\n</pre></html>"""
        pages = {"index-headers": hdr,
                 "index.json": b'{"directory":{"item":[{"name":"primary_doc.xml"},{"name":"0001-index.htm"}]}}',
                 "primary_doc.xml": b"<edgarSubmission><coverPageHeaderReportingPersonDetails><percentOfClass>16.4</percentOfClass></coverPageHeaderReportingPersonDetails></edgarSubmission>"}
        real = F.get
        F.get = lambda url, **kw: next((v for k, v in pages.items() if url.endswith(k) or (k == "index-headers" and "index-headers" in url)), None)
        try:
            d = F.stake_detail(1345471, "0000000000-26-000001")
        finally:
            F.get = real
        self.assertEqual((d["subject"], d["subjectCik"], d["pct"]), ("WENDY'S CO", 30697, 16.4))
        old = b"(11) PERCENT OF CLASS REPRESENTED BY AMOUNT IN ROW (9)\n\n      9.8%\n"
        self.assertEqual(float(F.PCT[1].search(old).group(1)), 9.8)
        rows = I.stake_summary([
            {"acc": "a1", "form": "SC 13D", "filed": "2024-01-02", "subject": "WENDY'S CO", "subjectCik": 30697, "pct": 12.0, "cik": 1},
            {"acc": "a2", "form": "SC 13D/A", "filed": "2025-03-01", "subject": "WENDY'S CO", "subjectCik": 30697, "pct": 4.2, "cik": 1},
            {"acc": "b1", "form": "SC 13G", "filed": "2024-06-01", "subject": "OTHER INC", "subjectCik": 5, "pct": None, "cik": 1}], {30697: "WEN"}, {"WEN": "US-WEN"}, {"WEN": "Wendy's"})
        self.assertEqual([r["ticker"] for r in rows], ["WEN", ""])
        self.assertEqual((rows[0]["n"], rows[0]["pctFirst"], rows[0]["pct"], rows[0]["below5"], rows[0]["active"]), (2, 12.0, 4.2, True, True))

    def test_13f_prices(self):
        import datetime as dt
        import fetch_13f_prices as P
        ts = lambda d: int(dt.datetime.fromisoformat(d).replace(tzinfo=dt.timezone.utc).timestamp())
        days = ["2024-03-28", "2024-04-01", "2024-04-30", "2024-05-15", "2024-05-31"]
        chart = {"chart": {"result": [{"meta": {"currency": "USD"}, "timestamp": [ts(d) for d in days],
                 "indicators": {"quote": [{"close": [10, 11, 12, 13, 14]}], "adjclose": [{"adjclose": [9.5, 10.5, 11.5, 12.5, 14]}]}}]}}
        d, tr, cl = P.parse(chart)
        self.assertEqual(d, days)
        self.assertEqual(tr[0], 9.5)       # total-return (dividend-adjusted) closes for returns
        self.assertEqual(cl[0], 10)        # split-adjusted closes for checking against filings
        # filed $10 at the quarter end matches; filed $40 matches after a later 4-for-1 split; $25 doesn't
        self.assertEqual(P.verified({"2024-03-31": 10.2}, d, cl), ["2024-03-31"])
        self.assertEqual(P.verified({"2024-03-31": 40.0}, d, cl), ["2024-03-31"])
        self.assertEqual(P.verified({"2024-03-31": 25.0}, d, cl), [])
        self.assertEqual(P.yahoo("BRK.B"), "BRK-B")
        cal = ["2024-02-14", "2024-02-15", "2024-02-29", "2024-03-28", "2024-05-15", "2024-05-16", "2024-05-31"]
        docs = [{"filings": [
            {"period": "2023-12-31", "filed": "2024-02-14", "holdings": [{"ticker": "XYZ", "value": 50, "shares": 5}, {"ticker": "SPX1", "value": 50, "shares": 1}]},
            {"period": "2024-03-31", "filed": "2024-05-15", "holdings": [{"ticker": "XYZ", "value": 100, "shares": 10}]}]}]
        n = P.needs(docs, cal, {"SPX1"})
        self.assertEqual(set(n), {"XYZ"})
        self.assertTrue({"2024-02-15", "2024-02-29", "2024-05-16"} <= n["XYZ"]["days"])
        self.assertEqual(n["XYZ"]["checks"]["2024-03-31"], 10)
        self.assertEqual(n["XYZ"]["latestw"], 1.0)

    def test_patterns(self):
        import investors as I
        # a 10-for-1 split is not a purchase
        a, b = {"shares": 100, "value": 10000}, {"shares": 1000, "value": 11000}
        self.assertEqual(I.split_factor(a, b), 10)
        self.assertAlmostEqual(I.share_change(a, b), 0.0)
        self.assertAlmostEqual(I.share_change({"shares": 100, "value": 100}, {"shares": 150, "value": 160}), 0.5)
        # money leaving the fund (every holding cut alike) is not trading; switching is
        prev = {"A": {"shares": 100, "value": 500}, "B": {"shares": 100, "value": 500}}
        out = {"A": {"shares": 50, "value": 250}, "B": {"shares": 50, "value": 250}}
        self.assertAlmostEqual(I.turnover(prev, out), 0.0)
        swap = {"A": {"shares": 100, "value": 500}, "C": {"shares": 10, "value": 500}}
        self.assertAlmostEqual(I.turnover(prev, swap), 0.5)
        # share classes are one company
        self.assertEqual(I.company("Alphabet Inc. (Class A)"), I.company("Alphabet Inc. (Class C)"))
        # calendar-year returns from month-end points
        pts = [["2020-11-30", 1.0, 1.0], ["2020-12-31", 1.1, 1.0], ["2021-12-31", 1.21, 1.1], ["2022-03-31", 1.21, 1.0]]
        ys = I.yearly(pts)
        self.assertEqual([y["year"] for y in ys], [2020, 2021, 2022])
        self.assertAlmostEqual(ys[1]["ret"], 0.1, places=4)
        self.assertTrue(ys[0]["partial"] and ys[2]["partial"] and not ys[1]["partial"])
        # a holding with no price on the buying day is left out and the rest re-weighted
        days = ["2024-01-02", "2024-01-03", "2024-01-31", "2024-02-29"]
        px = {"AAA": (days, [10, 10, 10.5, 11]), "NEW": (["2024-01-31", "2024-02-29"], [5, 5])}
        doc = {"filings": [{"filed": "2024-01-02", "holdings": [{"ticker": "AAA", "value": 1, "cusip": "X"}, {"ticker": "NEW", "value": 99, "cusip": "Y"}]}]}
        r = I.copy_record(doc, px, (days, [100, 100, 100, 100]))
        self.assertAlmostEqual(r["total"], 0.1, places=6)



class UnitStepTest(unittest.TestCase):
    def test_pounds_stretch_is_put_in_pence(self):
        from sync_uk_prices import fix_unit_steps
        # Baltic Classifieds: 16,809p then 169p the next day (the older stretch was 100x too high)
        bars = [["2026-08-20", 16500, 16900, 16400, 16700, 1], ["2026-08-21", 16700, 16900, 16600, 16809, 1],
                ["2026-08-24", 168, 171, 167, 169.1, 1], ["2026-08-25", 169, 172, 168, 170, 1]]
        out, steps = fix_unit_steps(bars)
        self.assertEqual(steps, 1)
        self.assertEqual([b[4] for b in out], [167.0, 168.09, 169.1, 170])

    def test_one_bad_day_cancels_out(self):
        from sync_uk_prices import fix_unit_steps
        bars = [["d1", 0, 0, 0, 200, 1], ["d2", 0, 0, 0, 2.01, 1], ["d3", 0, 0, 0, 202, 1]]
        out, steps = fix_unit_steps(bars)
        self.assertEqual([b[4] for b in out], [200, 201.0, 202])
        self.assertEqual(steps, 2)

    def test_real_moves_are_kept(self):
        from sync_uk_prices import fix_unit_steps
        bars = [["d1", 0, 0, 0, 100, 1], ["d2", 0, 0, 0, 40, 1], ["d3", 0, 0, 0, 90, 1]]
        self.assertEqual(fix_unit_steps(bars), (bars, 0))
