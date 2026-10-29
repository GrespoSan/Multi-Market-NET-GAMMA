"""ETF-option Gamma may be mapped only as a clearly labeled future overlay."""
import unittest
from datetime import date

from etf_future_pine import make_etf_future_pine


DAY = date(2026, 10, 29)
FRIDAY = date(2026, 10, 30)


def group(exp, base=366):
    return {"expiry": exp.isoformat(), "usable": True,
            "rows": [{"strike": float(base+i), "net": (-1)**i * (i+1)*.17}
                     for i in range(3)]}


class PineFutureTests(unittest.TestCase):
    def test_gold_pine_only_gold_futures_and_preserves_gammas(self):
        main = group(DAY)
        week = group(FRIDAY)
        script = make_etf_future_pine(
            "GLD", {"0DTE": main, "Weekly": week}, 366.1, DAY, "0DTE + Weekly")
        self.assertIn("//@version=6", script)
        self.assertIn('syminfo.root == "GC"', script)
        self.assertIn('syminfo.root == "MGC"', script)
        self.assertNotIn('syminfo.root == "CL"', script)
        self.assertIn('syminfo.type == "futures"', script)
        self.assertIn('indicator("Multi-Market NET GAMMA · GLD', script)
        self.assertIn("0DTE 29/10", script)
        self.assertIn("Weekly 30/10", script)
        self.assertIn("float yPrice = ref * etfStrike / 366.1", script)
        self.assertIn("futureAnchorManual = input.float(0.0", script)
        self.assertIn('request.security(syminfo.tickerid, "D", close[1]', script)
        self.assertIn('Gamma/barra', script)
        self.assertIn("NON opzioni native del future", script)
        self.assertIn("array.from(", script)
        self.assertIn("0.17", script)
        self.assertIn("-0.34", script)
        self.assertEqual(main["rows"][0]["strike"], 366.)
        self.assertEqual(main["rows"][1]["net"], -.34)

    def test_oil_pine_only_oil_futures(self):
        script = make_etf_future_pine("USO", {"0DTE": group(DAY, 70)},
                                      70.5, DAY, "Solo 0DTE")
        self.assertIn('syminfo.root == "CL"', script)
        self.assertIn('syminfo.root == "MCL"', script)
        self.assertNotIn('syminfo.root == "GC"', script)
        self.assertIn("float yPrice = ref * etfStrike / 70.5", script)
        self.assertIn('0DTE 29/10', script)
        self.assertNotIn("Weekly 30/10", script)
        self.assertIn("array.new_float()", script)

    def test_non_current_primary_does_not_claim_0dte(self):
        main = group(date(2026, 10, 28))
        script = make_etf_future_pine("USO", {"Principale": main},
                                      70.0, date(2026, 10, 28), "Solo Principale")
        self.assertIn("Principale 28/10", script)
        self.assertNotIn('"0DTE 28/10"', script)

    def test_wrong_assets_incomplete_profiles_rejected(self):
        with self.assertRaisesRegex(ValueError, "Sottostante"):
            make_etf_future_pine("CL", {"0DTE": group(DAY)}, 70, DAY, "test")
        with self.assertRaisesRegex(ValueError, "non completo"):
            p = group(DAY)
            p["usable"] = False
            make_etf_future_pine("USO", {"0DTE": p}, 70, DAY, "test")
        with self.assertRaisesRegex(ValueError, "Close precedente"):
            make_etf_future_pine("GLD", {"0DTE": group(DAY)}, 0, DAY, "test")

    def test_refuse_over_line_budget_instead_of_truncating(self):
        p = group(DAY)
        p["rows"] = [{"strike": float(i+1), "net": .001} for i in range(481)]
        with self.assertRaisesRegex(ValueError, "480"):
            make_etf_future_pine("USO", {"0DTE": p}, 70, DAY, "test")

    def test_code_does_not_embed_invalid_multiline_label_string(self):
        script = make_etf_future_pine("GLD", {"0DTE": group(DAY)}, 366, DAY, "Solo 0DTE")
        self.assertIn(r"NON gamma future\nAncora future", script)
        self.assertNotIn("NON gamma future\nAncora future", script)

    def test_empty_weekly_or_main_does_not_invent(self):
        weekly = make_etf_future_pine("USO", {"Weekly": group(FRIDAY)},
                                      70, DAY, "Solo Weekly")
        self.assertIn("Weekly 30/10", weekly)
        self.assertIn("// Profilo principale assente", weekly)
        self.assertIn("array.new_float()", weekly)


if __name__ == "__main__":
    unittest.main()
