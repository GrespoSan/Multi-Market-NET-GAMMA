"""Regression tests for new RUT/RTY and DJX/YM principal markets.

Pure synthetic CBOE contracts only; no network activity or vendor access.
"""
import ast
import unittest
from datetime import date
from pathlib import Path
from v2_index_basis import dated_contract, CONFIG
from v2_universal_cboe import _pine, parse_contract, profile

ROOT = Path(__file__).resolve().parent.parent


class IndexMarketTests(unittest.TestCase):
    def test_python_sources_parse(self):
        for module in ("app.py", "markets.py", "v2_index_market_view.py",
                       "v2_index_basis.py", "v2_universal_cboe.py",
                       "v2_market_engine.py", "v2_cron.py"):
            with self.subTest(module=module):
                ast.parse((ROOT / module).read_text(encoding="utf-8"))

    def test_quarterly_contracts_respect_future_root(self):
        self.assertEqual(dated_contract("RUT", date(2026, 11, 11))["ticker"], "RTYZ6")
        self.assertEqual(dated_contract("DJX", date(2026, 11, 11))["ticker"], "YMZ6")
        self.assertEqual(CONFIG["DJX"]["factor"], 100.0)
        self.assertEqual(CONFIG["RUT"]["factor"], 1.0)

    def test_weeklies_cboe_contract_roots(self):
        for root, weekly in (("RUT", "RUTW"), ("DJX", "DJXW")):
            contract = {"option": weekly + "261113C" + "02800000"}
            self.assertEqual(parse_contract(contract, root)[0], date(2026, 11, 13))

    def test_rut_future_pine_keeps_gamma_and_adds_basis(self):
        groups = {"0DTE": {
            "expiry": date(2026, 11, 11),
            "rows": [{"strike": 2810.0, "net": 5.0},
                     {"strike": 2820.0, "net": -4.0}]
        }}
        pine = _pine("RUT", groups, future_mode=True, future_basis=11.5)
        self.assertIn('syminfo.root == "RTY"', pine)
        self.assertIn('syminfo.root == "M2K"', pine)
        self.assertIn("indexFutureBasis = input.float(11.5000", pine)
        self.assertIn("float basisFactor = 1.0", pine)
        self.assertIn("renderProfile(plotMainLevels", pine)
        self.assertIn("array.push(plotMainLevels, level * basisFactor + displayBasis)", pine)
        self.assertIn("5.0", pine)
        self.assertIn("-4.0", pine)

    def test_dow_future_pine_converts_only_price_coordinates(self):
        groups = {"0DTE": {
            "expiry": date(2026, 11, 11),
            "rows": [{"strike": 520.0, "net": 6.0},
                     {"strike": 521.0, "net": -3.0}]
        }}
        pine = _pine("DJX", groups, future_mode=True, future_basis=38.0)
        self.assertIn('syminfo.root == "YM"', pine)
        self.assertIn('syminfo.root == "MYM"', pine)
        self.assertIn("float basisFactor = 100.0", pine)
        self.assertIn("indexFutureBasis = input.float(38.0000", pine)
        self.assertIn("renderProfile(plotMainLevels", pine)
        self.assertIn("6.0", pine)
        self.assertIn("-3.0", pine)

    def test_universal_djx_remains_original_indice_not_future(self):
        groups = {"0DTE": {
            "expiry": date(2026, 11, 11),
            "rows": [{"strike": 520.0, "net": 6.0},
                     {"strike": 521.0, "net": -3.0}]
        }}
        pine = _pine("DJX", groups)
        self.assertIn('validTicker = syminfo.ticker == "DJX"', pine)
        self.assertNotIn("basisFactor", pine)


if __name__ == "__main__":
    unittest.main()
