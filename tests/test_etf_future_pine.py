"""Regression tests for frozen synchronized-ratio ETF → related future Pine."""
import unittest
from datetime import date

from etf_future_pine import make_etf_future_pine

DAY = date(2026, 10, 29)
FRIDAY = date(2026, 10, 30)


def group(exp, base=366):
    return {"expiry": exp.isoformat(), "usable": True,
            "rows": [{"strike": float(base+i), "net": (-1)**i * (i+1)*.17}
                     for i in range(3)]}


def locked(symbol="GLD"):
    is_gold = symbol == "GLD"
    ep = 368.36 if is_gold else 167.46
    fp = 4070.10 if is_gold else 101.14
    return {"etf_symbol": symbol, "etf_price": ep, "future_price": fp,
            "ratio": fp / ep, "bar_ny": "2026-10-29T15:30:00-04:00",
            "future_tv_symbol": "COMEX:GCZ2026" if is_gold else "NYMEX:CLZ2026",
            "source": "Yahoo Finance · 5m same-timestamp completed bars"}


class PineFutureTests(unittest.TestCase):
    def test_gold_frozen_ratio_on_correct_futures_and_preserves_gamma(self):
        main, week = group(DAY), group(FRIDAY)
        script = make_etf_future_pine(
            "GLD", {"0DTE": main, "Weekly": week}, 366.1,
            DAY, "0DTE + Weekly", locked())
        self.assertIn("//@version=6", script)
        self.assertIn('syminfo.root == "GC"', script)
        self.assertIn('syminfo.root == "MGC"', script)
        self.assertNotIn('syminfo.root == "CL"', script)
        self.assertIn('syminfo.type == "futures"', script)
        self.assertIn("0DTE 29/10", script)
        self.assertIn("if barstate.islast and validTicker", script)
        self.assertIn("Weekly 30/10", script)
        self.assertIn('modeRatio = input.string("Bloccato"', script)
        self.assertIn('string contractTicker = "COMEX:GCZ2026"', script)
        self.assertIn('string etfTicker = "AMEX:GLD"', script)
        self.assertIn("array.push(resultLevels, etfStrike * ratio)", script)
        self.assertNotIn("futureAnchorManual", script)
        self.assertNotIn("futureDailyPrevious", script)
        self.assertIn("etfTime == futTime", script)
        self.assertIn("close[1], time[1]", script)
        self.assertIn("Gamma/barra", script)
        self.assertIn("NON opzioni native del future", script)
        self.assertIn("0.17", script)
        self.assertIn("-0.34", script)
        self.assertEqual(main["rows"][0]["strike"], 366)
        self.assertEqual(main["rows"][1]["net"], -.34)
        self.assertIn('float lockedRatio = 11.049', script)

    def test_oil_frozen_ratio_and_weekly_absent(self):
        script = make_etf_future_pine("USO", {"0DTE": group(DAY, 170)},
                                      170., DAY, "Solo 0DTE", locked("USO"))
        self.assertIn('syminfo.root == "CL"', script)
        self.assertIn('syminfo.root == "MCL"', script)
        self.assertNotIn('syminfo.root == "GC"', script)
        self.assertIn("array.push(resultLevels, etfStrike * ratio)", script)
        self.assertIn("0DTE 29/10", script)
        self.assertNotIn("Weekly 30/10", script)
        self.assertIn("array.new_float()", script)
        self.assertIn("float lockedRatio = 0.603", script)

    def test_non_current_primary_does_not_claim_0dte(self):
        script = make_etf_future_pine(
            "USO", {"Principale": group(date(2026, 10, 28), 170)},
            170., date(2026, 10, 28), "Solo Principale", locked("USO"))
        self.assertIn("Principale 28/10", script)
        self.assertNotIn('"0DTE 28/10"', script)

    def test_missing_or_inconsistent_ratio_blocks_export(self):
        with self.assertRaisesRegex(ValueError, "rapporto"):
            make_etf_future_pine("GLD", {"0DTE": group(DAY)}, 366, DAY,
                                 "test", None)
        x = locked()
        x["ratio"] = 123.0
        with self.assertRaisesRegex(ValueError, "incoerente"):
            make_etf_future_pine("GLD", {"0DTE": group(DAY)}, 366, DAY,
                                 "test", x)
        with self.assertRaisesRegex(ValueError, "Sottostante"):
            make_etf_future_pine("CL", {"0DTE": group(DAY)}, 366, DAY,
                                 "test", locked())

    def test_wrong_contract_and_incomplete_profiles_rejected(self):
        x = locked()
        x["future_tv_symbol"] = "NYMEX:CLZ2026"
        with self.assertRaisesRegex(ValueError, "Contratto future"):
            make_etf_future_pine("GLD", {"0DTE": group(DAY)}, 366, DAY,
                                 "test", x)
        p = group(DAY)
        p["usable"] = False
        with self.assertRaisesRegex(ValueError, "non completo"):
            make_etf_future_pine("GLD", {"0DTE": p}, 366, DAY, "test", locked())

    def test_too_many_lines_not_truncated(self):
        p = group(DAY)
        p["rows"] = [{"strike": float(i+1), "net": .001} for i in range(481)]
        with self.assertRaisesRegex(ValueError, "480"):
            make_etf_future_pine("USO", {"0DTE": p}, 170, DAY,
                                 "test", locked("USO"))

    def test_context_ratio_notice_is_not_drawn_on_the_future_chart(self):
        code = make_etf_future_pine(
            "GLD", {"0DTE": group(DAY)}, 366, DAY, "Solo 0DTE", locked())
        self.assertNotIn('showContext = input.bool', code)
        self.assertNotIn('label notice = label.new', code)
        self.assertNotIn('array.push(drawnLabels, notice)', code)
        self.assertNotIn('ETF Gamma, NON CME/NYMEX', code)
        self.assertIn('Contratto future riferimento: COMEX:GCZ2026', code)
        self.assertIn('ratio 11.049', code)

    def test_only_weekly_does_not_invent_main_profile(self):
        code = make_etf_future_pine(
            "USO", {"Weekly": group(FRIDAY, 170)}, 170., DAY,
            "Solo Weekly", locked("USO"))
        self.assertIn("Weekly 30/10", code)
        self.assertIn("// Profilo principale assente", code)
        self.assertIn("array.new_float()", code)


if __name__ == "__main__":
    unittest.main()
