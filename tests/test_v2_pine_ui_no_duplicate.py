"""Regression: three visible scheduled Pine exports, no duplicate current Pine."""
import ast
from pathlib import Path
import unittest
from v2_pine_session import SLOTS, LEGACY_SLOTS, slots_for_day
from v2_pine_timed_exports import EXPLANATIONS

ROOT = Path(__file__).resolve().parents[1]


def source(path):
    text = (ROOT / path).read_text(encoding="utf-8")
    ast.parse(text)
    return text


class TimedPineUILayout(unittest.TestCase):
    def test_new_and_historic_slot_triplets(self):
        from datetime import date
        self.assertEqual(SLOTS, ("0730", "1550", "1700"))
        self.assertEqual(LEGACY_SLOTS, ("0730", "1550", "2030"))
        self.assertEqual(slots_for_day(date(2026,11,11))[-1], "2030")
        self.assertEqual(slots_for_day(date(2026,11,12))[-1], "1700")
        self.assertEqual(slots_for_day(date(2026,11,16)),
                         ("0730", "1616", "1746"))
        self.assertIn("17:00", EXPLANATIONS["1700"])
        self.assertIn("20:30", EXPLANATIONS["2030"])

    def test_three_buttons_and_copy_panel(self):
        timed = source("v2_pine_timed_exports.py")
        self.assertIn('st.columns(3, gap="small")', timed)
        self.assertIn("zip(cols, slots_for_day(day))", timed)
        self.assertIn('"Scarica Pine · " + EXPLANATIONS[slot]', timed)
        self.assertIn('"Pine orario"', timed)
        self.assertIn('"Aggiorna Pine per orari"', timed)

    def test_ndx_no_duplicate_current_download(self):
        ndx = source("v2_market_engine.py")
        self.assertNotIn('NDX_NET_GAMMA_CORRENTE_', ndx)
        self.assertIn("render_timed_pine_exports(", ndx)
        self.assertIn("slots_for_day(day)", ndx)
        self.assertNotIn('with st.expander("Pine per orari', ndx)

    def test_gold_oil_shared_ui_and_principal_fallback(self):
        view = source("etf_pine_view.py")
        self.assertIn('render_timed_pine_exports(', view)
        self.assertIn('slots_for_day(day)', view)
        self.assertIn('PRINCIPALE NON 0DTE', view)
        self.assertIn("make_etf_future_pine(", view)
        self.assertNotIn('with st.expander("Pine per orari', view)

    def test_real_schedule_generator(self):
        timed = source("v2_pine_timed_exports.py")
        self.assertIn('if slot == "0730":', timed)
        self.assertIn("make_pine_comparison_v2(", timed)
        self.assertIn('prev_slot = previous_slot_for(day, slot)', timed)
        self.assertIn("scripts[slot] = script", timed)


if __name__ == "__main__":
    unittest.main()
