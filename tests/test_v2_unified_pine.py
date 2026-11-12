"""Unified experimental Pine: no artificial 0DTE or Gamma normalization."""
import unittest
from datetime import date
from pathlib import Path
from v2_unified_pine import build_unified_pine, MARKETS


def record(symbol):
    return {
        "main": [{"strike_index": 25000.0, "net_gamma": 2.0}] if symbol == "NDX"
                else [{"strike": 100.0, "net": 2.0}],
        "weekly": [{"strike_index": 25010.0, "net_gamma": -1.0}] if symbol == "NDX"
                else [{"strike": 110.0, "net": -1.0}],
        "call": [], "put": [],
        "field_level": "strike_index" if symbol == "NDX" else "strike",
        "field_gamma": "net_gamma" if symbol == "NDX" else "net",
        "scale": 0.1, "main_label": "0DTE",
        "main_expiry": date(2026, 11, 12),
        "weekly_expiry": date(2026, 11, 13),
        "captured": {"stamp": "12/11/2026 07:31 CET"},
        "basis": 50.0 if symbol == "NDX" else 0.0,
    }


class UnifiedPineTests(unittest.TestCase):
    def test_full_five_markets_single_pine(self):
        source = build_unified_pine(
            date(2026, 11, 12), {name: record(name) for name in MARKETS})
        self.assertEqual(source.count("//@version=6"), 1)
        self.assertEqual(source.count('indicator("'), 1)
        for asset in ("NDX", "RUT", "DJX", "GLD", "USO"):
            self.assertIn(f"var array<float> {asset}Levels", source)
            self.assertIn(f'"{asset}" =>', source)
        for root in ("NQ", "MNQ", "RTY", "M2K", "YM", "MYM", "GC", "MGC", "CL", "MCL"):
            self.assertIn(root, source)
        self.assertIn("etfTime == futTime", source)
        self.assertIn("lastDynamicRatio := futLast / etfLast", source)
        self.assertIn("float priceFactor = isYM ? 100.0 : 1.0", source)
        self.assertNotIn("@ARRAYS@", source)
        self.assertIn("renderProfile(", source)

    def test_gc_cl_on_15m_use_synchronized_confirmed_intrabar_pairs(self):
        src = build_unified_pine(
            date(2026, 11, 12), {name: record(name) for name in MARKETS})
        self.assertIn('request.security_lower_tf(etfTicker, "5", [close[1], time[1]]', src)
        self.assertIn('request.security_lower_tf(futureTicker, "5", [close[1], time[1]]', src)
        self.assertIn('if timeframe.in_seconds() <= 300', src)
        self.assertIn('while i >= 0 and j >= 0', src)
        self.assertIn('et > lastMatchedTime', src)
        self.assertIn('ep > 0 and fp > 0', src)
        self.assertIn('timeframe.isintraday and not na(ratioToDraw)', src)
        self.assertNotIn('timeframe.in_seconds() <= 300 and not na(ratioToDraw)', src)
        self.assertIn('string etfTicker = isGC ? "AMEX:GLD" : "AMEX:USO"', src)
        self.assertIn('string futureTicker = ticker.standard(syminfo.tickerid)', src)

    def test_missing_market_not_silently_filled(self):
        source = build_unified_pine(date(2026, 11, 12), {"NDX": record("NDX")})
        self.assertIn("var array<float> USOLevels = array.new_float()", source)
        self.assertIn("Fotografia/basis non disponibile", source)

    def test_no_0dte_label_when_principal(self):
        market = record("USO")
        market["main_label"] = "Principale (non 0DTE)"
        market["main_expiry"] = date(2026, 11, 13)
        source = build_unified_pine(date(2026, 11, 12), {"USO": market})
        self.assertIn('=> "Principale (non 0DTE)"', source)
        self.assertIn('showTop3Odte and mainKind == "0DTE"', source)

    def test_deployed_view_is_opt_in(self):
        app = (Path(__file__).resolve().parents[1] / "app.py").read_text()
        self.assertIn("render_unified_0730()", app)
        src = (Path(__file__).resolve().parents[1] / "v2_unified_pine.py").read_text()
        self.assertIn('expanded=False', src)
        self.assertIn('load_pine_slot_captures(symbol, market_day)', src)


if __name__ == "__main__":
    unittest.main()
