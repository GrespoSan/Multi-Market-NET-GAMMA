"""Trend Daily and the Daily-range card must consume identical Massive session OHLC.

No Yahoo, Massive network, Cboe, or Supabase calls during these tests.
"""
import unittest
from datetime import date
from pathlib import Path

from massive_futures_daily import parse_session, previous_daily_context
from v2_trend_daily import massive_frame, evaluate, impulse_reference

ROOT=Path(__file__).resolve().parent.parent

def bar(d, op, hi, lo, close, ticker="NQZ6"):
    return parse_session({
        "ticker":ticker, "session_end_date":d,
        "open":op,"high":hi,"low":lo,"close":close,
        "settlement_price": 111111.0, # deliberately irrelevant
    }, ticker)


class TrendFromMassiveTests(unittest.TestCase):
    def sample(self):
        return [
            bar("2026-10-23",29600.,29900.,29450.,29500.),
            bar("2026-10-26",29500.,29650.,29150.,29350.),
            bar("2026-10-27",29350.,29881.25,29288.,29803.5),
            bar("2026-10-28",29814.25,30178.,29674.25,29756.25),
            bar("2026-10-29",29793.5,29794.25,29111.,29218.25),
        ]

    def test_nq_range_identical_in_both_sections_and_baricentro(self):
        rows=self.sample()
        daily=previous_daily_context(rows[-2:])
        frame=massive_frame(rows,date(2026,10,30),contract="NQZ6")
        trend=evaluate(frame)
        self.assertAlmostEqual(daily["range_points"],683.25)
        self.assertEqual(daily["range_trend"],"ESPANSIONE")
        self.assertAlmostEqual(trend["range_pct"],daily["range_pct"],places=5)
        self.assertEqual(trend["range_shape"],"ESPANSIONE")
        self.assertAlmostEqual(trend["midpoint"],29452.625,places=3)
        self.assertAlmostEqual(trend["last_close"],29218.25)
        self.assertEqual(trend["midpoint_state"],"SOTTO")
        self.assertAlmostEqual(trend["midpoint_delta_pct"],-0.79577,places=3)
        self.assertEqual(trend["direction"],"RIBASSISTA")
        self.assertEqual(trend["bar_color"],"ROSSA")
        self.assertEqual(trend["same_color"],1)

    def test_no_lookahead_for_target_date(self):
        rows=self.sample()
        rows.append(bar("2026-10-30",29000.,29500.,28000.,28300.))
        frame=massive_frame(rows,date(2026,10,30),contract="NQZ6")
        self.assertEqual(len(frame),5)
        self.assertEqual(frame.iloc[-1]["Close"],29218.25)

    def test_missing_open_or_wrong_contract_gives_no_fabricated_candle(self):
        rows=self.sample()
        rows[-1]={**rows[-1], "open":None}
        with self.assertRaisesRegex(ValueError,"manca Open"):
            massive_frame(rows,date(2026,10,30),contract="NQZ6")
        rows=self.sample()
        rows[-1]={**rows[-1],"ticker":"GCZ6"}
        with self.assertRaisesRegex(ValueError,"contratti Massive"):
            massive_frame(rows,date(2026,10,30),contract="NQZ6")

    def test_ui_removes_second_range_and_yahoo_futures(self):
        trend=(ROOT/"v2_trend_daily.py").read_text()
        context=(ROOT/"v2_context.py").read_text()
        volatility=(ROOT/"v2_volatility.py").read_text()
        self.assertNotIn('>Range</div>',trend)
        self.assertNotIn('>Variazione del range</div>',trend)
        self.assertNotIn("yf.download",trend)
        self.assertNotIn("Yahoo Finance",trend)
        self.assertIn("Chiusura vs baricentro",trend)
        self.assertIn("Baricentro Daily",trend)
        self.assertIn("daily_bars=daily_context.get",context)
        self.assertIn('daily_context = render_volatility(market, reference_day)',context)
        self.assertIn('result["daily_bars"] = future_bars',volatility)
        self.assertIn('history_days=75',volatility)

if __name__ == "__main__":
    unittest.main()
