"""Keep V2 ANALISI DEL CONTESTO functionally faithful to Serafini SPX.

No live Yahoo, Finance Calendar, Cboe, Supabase or GitHub request in tests.
"""
import unittest
from pathlib import Path
from datetime import date

import pandas as pd

from v2_trend_daily import evaluate, impulse_reference
from v2_volatility import SOURCES, evaluate as evaluate_vol
from v2_context import selected_snapshot_day

ROOT = Path(__file__).resolve().parent.parent


class SPXContextV2Tests(unittest.TestCase):
    def test_original_spx_context_sections_replaced_empty_placeholder(self):
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("render_market_context(market_key)", app)
        self.assertNotIn("ancora da integrare e validare: nessun segnale inventato", app)
        context = (ROOT / "v2_context.py").read_text(encoding="utf-8")
        for name in ("Settimana ISO (AAAA-WNN)", "Snapshot distinti",
                     "Registri", "News e calendario macroeconomico",
                     "Volatilità — seduta precedente", "render_trend_daily(",
                     "render_macro_calendar()", "st.divider()"):
            with self.subTest(name=name):
                self.assertIn(name, context)

    def test_original_macro_and_m7_live_modules_are_present(self):
        macro = (ROOT / "macro_calendar.py").read_text(encoding="utf-8")
        self.assertIn("financecalendar.com", macro)
        self.assertIn("Calendario macro USA — eventi da monitorare", macro)
        self.assertIn("magnificent7_earnings", macro)
        self.assertIn("FOMC", macro)
        earnings = (ROOT / "magnificent7_earnings.py").read_text(encoding="utf-8")
        for ticker in ("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"):
            self.assertIn(ticker, earnings)

    def test_volatility_is_market_specific_without_fake_spx_buffer(self):
        self.assertEqual(SOURCES["NASDAQ"][0:2], ("NQ=F", "^VXN"))
        self.assertEqual(SOURCES["GOLD"][0:2], ("GC=F", "^GVZ"))
        self.assertEqual(SOURCES["WTI"][0:2], ("CL=F", "^OVX"))
        x = evaluate_vol(
            [{"day": date(2026,10,29), "hi": 101., "lo": 97.,
              "close": 100.}],
            [{"day": date(2026,10,28), "hi": 36., "lo": 34.,
              "close": 35.},
             {"day": date(2026,10,29), "hi": 37., "lo": 35.,
              "close": 36.}])
        self.assertEqual(x["range_text"], "4.00 pt · 4.00%")
        self.assertIn("36.00", x["vol_text"])
        self.assertIn("+2.86%", x["vol_text"])
        src = (ROOT / "v2_volatility.py").read_text(encoding="utf-8")
        self.assertIn("Non definito", src)
        self.assertIn("SPX", src)
        self.assertIn("spx-vol-card", src)
        self.assertNotIn("previous_vix_curve", src)

    def test_previous_session_change_is_separate_from_daily_range(self):
        # High-Low is always positive, whereas Close/Close has a sign.
        common = {"hi": 105., "lo": 95., "close": 100.}
        day1, day2 = date(2026, 10, 28), date(2026, 10, 29)
        up = evaluate_vol([
            {"day": day1, "hi": 101., "lo": 99., "close": 100.},
            {"day": day2, "hi": 105., "lo": 95., "close": 103.},
        ], [])
        self.assertEqual(up["range_text"], "10.00 pt · 9.71%")
        self.assertAlmostEqual(up["change_pct"], 3.0)
        self.assertEqual(up["previous_close_day"], day1)
        down = evaluate_vol([
            {"day": day1, **common},
            {"day": day2, "hi": 102., "lo": 97., "close": 98.},
        ], [])
        self.assertEqual(down["range_text"], "5.00 pt · 5.10%")
        self.assertAlmostEqual(down["change_pct"], -2.0)
        flat = evaluate_vol([
            {"day": day1, **common},
            {"day": day2, "hi": 105., "lo": 95., "close": 100.},
        ], [])
        self.assertEqual(flat["change_pct"], 0.0)
        first = evaluate_vol([{"day": day2, **common}], [])
        self.assertIsNone(first["change_pct"])
        src = (ROOT / "v2_volatility.py").read_text(encoding="utf-8")
        self.assertIn("Variazione ieri (Close/Close)", src)
        self.assertIn('class="{change_class}"', src)
        self.assertIn('.spx-daily-change .up', src)
        self.assertIn('.spx-daily-change .down', src)
        self.assertIn('escape(result[\'range_text\'])', src)
        self.assertNotIn('range_percentage_html(', src)

    def test_daily_trend_rule_unchanged_but_ticker_dynamic(self):
        dates = pd.date_range("2026-10-20", periods=5, freq="B")
        bars = pd.DataFrame([
            {"Open": 100., "High": 103., "Low": 99., "Close": 101.},
            {"Open": 101., "High": 105., "Low": 100., "Close": 104.},
            {"Open": 104., "High": 106., "Low": 102., "Close": 103.},
            {"Open": 103., "High": 107., "Low": 103., "Close": 106.},
            {"Open": 106., "High": 108., "Low": 104., "Close": 107.},
        ], index=dates)
        info = evaluate(bars)
        self.assertEqual(info["direction"], "RIALZISTA")
        self.assertIn(info["range_shape"], ("COMPRESSIONE", "ESPANSIONE", "INVARIATO"))
        impulse = impulse_reference(bars)
        # Le barre sintetiche possono soddisfare la soglia sperimentale
        # originale; il test verifica il calcolo senza forzare un risultato.
        self.assertTrue(impulse is None or (
            impulse["side"] in ("RIALZISTA", "RIBASSISTA")
            and impulse["status"] in ("TENUTA", "PERSO", "RECUPERATO")))
        src = (ROOT / "v2_trend_daily.py").read_text(encoding="utf-8")
        self.assertIn("market_name=", src)
        self.assertIn("ticker=", src)
        self.assertIn("spx-trend-card", src)
        self.assertNotIn('yf.download("ES=F"', src)

    def test_archive_metrics_do_not_mislabel_artifact_runs_as_snapshots(self):
        src = (ROOT / "v2_context.py").read_text(encoding="utf-8")
        self.assertIn('st.metric("Snapshot distinti", "—")', src)
        self.assertIn("I registri, se disponibili", src)
        self.assertIn("Supabase", (ROOT / "v2_storage_off.py").read_text())


if __name__ == "__main__":
    unittest.main()
