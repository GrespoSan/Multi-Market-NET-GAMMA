"""Regressioni fascia NDX: close precedente, ±1,5%, Gamma invariato, Pine."""
import unittest
from datetime import date

from ndx_engine import profile, DEFAULT_BAND_PCT
from pine_export import make_pine


FIRST = date(2026, 10, 29)
WEEKLY = date(2026, 10, 30)


def chain(step=5, max_distance=600):
    options = []
    for expiry in (FIRST, WEEKLY):
        for strike in range(30000 - max_distance, 30000 + max_distance + 1, step):
            for side, oi, vol, gamma in (("C", 10, 2, 0.1), ("P", 3, 1, 0.2)):
                symbol = f"NDXP{expiry:%y%m%d}{side}{strike*1000:08d}"
                options.append({"option": symbol, "open_interest": oi,
                                "volume": vol, "gamma": gamma})
    return {"symbol": "_NDX", "data": {"prev_day_close": 30000, "options": options}}


class TestPercentageStrikeSelection(unittest.TestCase):
    def test_unchanged_formula_and_all_strikes_in_common_band(self):
        doc = chain()
        a = profile(doc, FIRST, 30000, band_pct=1.5)
        b = profile(doc, WEEKLY, 30000, band_pct=1.5)
        self.assertEqual(DEFAULT_BAND_PCT, 3.0)
        self.assertAlmostEqual(a["band_lower"], 29550)
        self.assertAlmostEqual(a["band_upper"], 30450)
        self.assertEqual((a["band_lower"], a["band_upper"]),
                         (b["band_lower"], b["band_upper"]))
        self.assertEqual(a["selected_strikes"], 181)
        self.assertEqual(b["selected_strikes"], 181)
        self.assertEqual(a["rows"][0]["strike_index"], 29550)
        self.assertEqual(a["rows"][-1]["strike_index"], 30450)
        self.assertAlmostEqual(a["rows"][5]["call_gamma"], 1.2)
        self.assertAlmostEqual(a["rows"][5]["put_gamma"], 0.8)
        self.assertAlmostEqual(a["rows"][5]["net_gamma"], 0.4)

    def test_pine_exports_all_362_strikes_without_fixed_fifty_limit(self):
        doc = chain()
        a, b = profile(doc, FIRST, 30000, band_pct=1.5), profile(doc, WEEKLY, 30000, band_pct=1.5)
        code = make_pine({"0DTE": a, "Weekly": b}, 154.0087, FIRST, "29/10")
        self.assertIn("max_lines_count=500", code)
        self.assertIn("0DTE 29/10", code)
        self.assertIn("Weekly 30/10", code)
        self.assertIn("29704.008700", code)
        self.assertIn("30604.008700", code)

    def test_pine_blocks_over_line_limit_instead_of_truncating(self):
        doc = chain(step=2)
        a, b = profile(doc, FIRST, 30000), profile(doc, WEEKLY, 30000)
        with self.assertRaisesRegex(ValueError, "480"):
            make_pine({"0DTE": a, "Weekly": b}, 154, FIRST, "29/10")

    def test_custom_percentage_changes_both_profiles_not_gamma(self):
        doc = chain()
        narrow = profile(doc, FIRST, 30000, band_pct=0.5)
        wide0 = profile(doc, FIRST, 30000, band_pct=2.0)
        wideW = profile(doc, WEEKLY, 30000, band_pct=2.0)
        self.assertEqual((narrow["band_lower"], narrow["band_upper"]),
                         (29850.0, 30150.0))
        self.assertEqual((wide0["band_lower"],wide0["band_upper"]),
                         (29400.0,30600.0))
        self.assertEqual((wide0["band_lower"],wide0["band_upper"]),
                         (wideW["band_lower"],wideW["band_upper"]))
        self.assertGreater(wide0["selected_strikes"],narrow["selected_strikes"])
        self.assertAlmostEqual(narrow["rows"][0]["net_gamma"],
                               wide0["rows"][0]["net_gamma"])

    def test_empty_band_rejected(self):
        doc = chain(step=5, max_distance=600)
        with self.assertRaisesRegex(ValueError, "nessuno strike"):
            profile(doc, FIRST, 50000)


if __name__ == "__main__":
    unittest.main()
