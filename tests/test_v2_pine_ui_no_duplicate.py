"""Regression: retain all THREE scheduled Pine exports on every V2 market.

The current Pine and the 07:30 scheduled Pine are both intentional user-facing
controls. Never hide the 07:30 autonomous button to deduplicate the UI.
No changes to Gamma calculations or historical snapshot validation.
"""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

from v2_pine_session import SLOTS
from v2_pine_timed_exports import EXPLANATIONS, produce_timed_scripts

ROOT=Path(__file__).resolve().parents[1]


def source(name):
    code=(ROOT/name).read_text(encoding="utf-8")
    ast.parse(code, filename=name)
    return code


class AllThreeScheduledPinesUI(unittest.TestCase):
    def test_three_scheduled_buttons_always_in_order(self):
        self.assertEqual(tuple(SLOTS), ("0730","1550","2030"))
        timed=source("v2_pine_timed_exports.py")
        visible=timed[timed.index("def render_timed_pine_exports("):]
        self.assertIn("st.columns(3, gap=\"small\")",visible)
        self.assertIn("for col, slot in zip(cols, SLOTS):",visible)
        self.assertIn('"Scarica Pine · " + EXPLANATIONS[slot]',visible)
        self.assertIn('list(scripts)',visible)
        self.assertIn('"Pine orario"',visible)
        self.assertIn('"Aggiorna Pine per orari"',visible)
        self.assertIn("07:30",EXPLANATIONS["0730"])
        self.assertIn("15:50",EXPLANATIONS["1550"])
        self.assertIn("20:30",EXPLANATIONS["2030"])
        self.assertNotIn("COMPARISON_SLOTS",visible)

    def test_ndx_keeps_both_current_and_all_three_scheduled(self):
        ndx=source("v2_market_engine.py")
        self.assertIn('current_script = make_pine(',ndx)
        self.assertEqual(ndx.count(
            '"Scarica Pine NET GAMMA corrente · NQ/MNQ (.pine)"'),1)
        self.assertIn('acquisition_time=st.session_state.get("ndx_capture_rome_iso")',ndx)
        self.assertIn('with st.expander("Pine per orari · 07:30 / 15:50 / 20:30"',ndx)
        self.assertIn('render_timed_pine_exports(',ndx)
        self.assertLess(
            ndx.index('"Scarica Pine NET GAMMA corrente · NQ/MNQ (.pine)"'),
            ndx.index('with st.expander("Pine per orari'))
        self.assertIn('delle 07:30 rimane disponibile',ndx)

    def test_gold_and_oil_identical_original_current_and_three_slots(self):
        view=source("etf_pine_view.py")
        self.assertIn('st.subheader(f"Pine Script v6 · Future continuo {label}")',view)
        self.assertEqual(view.count('f"Scarica Pine NET GAMMA · {label} (.pine)"'),1)
        self.assertIn('continuous=True',view)
        self.assertIn('with st.expander("Pine per orari · 07:30 / 15:50 / 20:30"',view)
        self.assertEqual(view.count('render_timed_pine_exports('),1)
        self.assertLess(view.index('f"Scarica Pine NET GAMMA · {label} (.pine)"'),
                        view.index('with st.expander("Pine per orari'))
        self.assertNotIn('prepare_locked_chart_mapping',view)
        self.assertNotIn('fetch_oil_pair(',view)

    def test_generator_still_builds_real_0730_and_both_comparisons(self):
        timed=source("v2_pine_timed_exports.py")
        producer=timed[timed.index("def produce_timed_scripts("):
                       timed.index("def render_timed_pine_exports(")]
        self.assertIn('if slot == "0730":',producer)
        self.assertIn('make_pine_comparison_v2(',producer)
        self.assertIn('prev_slot = "0730" if slot == "1550" else "1550"',producer)
        self.assertIn('scripts[slot] = script',producer)


if __name__ == "__main__":
    unittest.main()
