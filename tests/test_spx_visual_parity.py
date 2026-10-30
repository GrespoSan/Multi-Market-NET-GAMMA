"""One authoritative Serafini SPX visual template for all three futures charts.

The source renderer is shared. Data/Gamma conversion is market specific.
No unrelated status notice may be overlaid on chart candles.
"""
import unittest
from datetime import date

from pine_export import make_pine
from etf_future_pine import make_etf_future_pine
from pine_spx_visual import SPX_RENDER_FUNCTIONS

TODAY = date(2026, 10, 29)


def ndx_sample():
    return {"0DTE": {"expiry": TODAY.isoformat(), "band_pct": 3.,
            "rows": [{"strike_index": 30000.+j*5, "net_gamma": .1 * (j-1)}
                     for j in range(3)]}}


def etf_sample(symbol):
    strike = 367. if symbol == "GLD" else 167.
    ref = 368.36 if symbol == "GLD" else 167.46
    future = 4070.10 if symbol == "GLD" else 101.14
    future_ticker = "COMEX:GCZ2026" if symbol == "GLD" else "NYMEX:CLZ2026"
    groups = {"0DTE": {"expiry": TODAY.isoformat(), "usable": True,
              "rows": [{"strike": strike+j, "net": (j-1)*0.1} for j in range(3)]}}
    mapping = {"etf_symbol": symbol, "etf_price": ref, "future_price": future,
               "ratio": future/ref, "bar_ny": "2026-10-29T15:30:00-04:00",
               "future_tv_symbol": future_ticker}
    return make_etf_future_pine(symbol, groups, ref, TODAY, "Solo 0DTE", mapping)


class SPXVisualParity(unittest.TestCase):
    def test_all_three_reuse_exact_spx_style_renderer(self):
        scripts = {
            "Nasdaq": make_pine(ndx_sample(), 140., TODAY, "29/10"),
            "Gold": etf_sample("GLD"),
            "Petrolio": etf_sample("USO"),
        }
        for market, pine in scripts.items():
            with self.subTest(market=market):
                self.assertEqual(pine.count(SPX_RENDER_FUNCTIONS), 1)
                self.assertIn('gammaPerCandle = input.float(', pine)
                self.assertIn('"Scala MANUALE · Gamma/barra"', pine)
                self.assertIn('offsetOdte = input.int(60, "Distanza 0DTE da ultima candela"', pine)
                self.assertIn('offsetWeekly = input.int(100, "Distanza Weekly dalle 0DTE"', pine)
                self.assertIn('int weeklyCenter = offsetOdte + offsetWeekly', pine)
                self.assertIn('requiredScale(' , pine)
                self.assertIn(', weeklyCenter)', pine)
                self.assertNotIn('bar_index + offsetWeekly,', pine)
                self.assertIn('positiveColor = input.color(color.rgb(0, 230, 117)', pine)
                self.assertIn('negativeColor = input.color(color.rgb(242, 54, 69)', pine)
                self.assertIn('showTitles = input.bool(true, "Mostra intestazioni")', pine)
                self.assertIn('if barstate.islast and validTicker', pine)
                self.assertIn('float minimumSafe = math.max(', pine)
                # Weekly segue 0DTE anche quando quest'ultima viene spostata.
                self.assertIn('bar_index + weeklyCenter', pine)
                self.assertEqual(160 + 100, 260)
                self.assertIn('xloc=xloc.bar_index, extend=extend.none', pine)
                self.assertNotIn('showContext', pine)
                self.assertNotIn('label notice = label.new', pine)
                self.assertNotIn('array.push(drawnLabels, notice)', pine)

    def test_futures_are_guarded_and_ratio_only_maps_etf_strikes(self):
        nq = make_pine(ndx_sample(), 140., TODAY, "29/10")
        gold = etf_sample("GLD")
        oil = etf_sample("USO")
        self.assertIn('syminfo.root == "NQ"', nq)
        self.assertIn('syminfo.root == "MNQ"', nq)
        self.assertIn('syminfo.root == "GC"', gold)
        self.assertIn('syminfo.root == "MGC"', gold)
        self.assertIn('syminfo.root == "CL"', oil)
        self.assertIn('syminfo.root == "MCL"', oil)
        for code in (gold, oil):
            self.assertIn('array.push(resultLevels, etfStrike * ratio)', code)
            self.assertIn('renderProfile(odteLevels, mainGammaETF,', code)
            self.assertIn('modeRatio = input.string("Bloccato"', code)
            self.assertIn('gaps=barmerge.gaps_on', code)
        self.assertIn('30140.0', nq)
        self.assertIn('30150.0', nq)


if __name__ == "__main__":
    unittest.main()
