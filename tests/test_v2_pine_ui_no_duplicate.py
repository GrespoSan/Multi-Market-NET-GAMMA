"""UI regression: exactly one current Pine and two real time comparisons.

Keeps old 07:30 generator for parity tests, but no second 07:30 button.
The selected Cboe archive photograph is the only source for current Pine.
No changes to Gamma formulas, archived comparisons or futures conversion.
"""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

from v2_pine_timed_exports import COMPARISON_SLOTS, EXPLANATIONS, produce_timed_scripts

ROOT = Path(__file__).resolve().parents[1]


def source(name):
    code=(ROOT/name).read_text(encoding="utf-8")
    ast.parse(code, filename=name)
    return code


class CurrentAndComparisonsUI(unittest.TestCase):
    def test_time_comparison_widget_has_exactly_two_options(self):
        self.assertEqual(COMPARISON_SLOTS, ("1550", "2030"))
        timed=source("v2_pine_timed_exports.py")
        visible=timed[timed.index("def render_timed_pine_exports("):]
        self.assertIn("st.columns(len(COMPARISON_SLOTS)", visible)
        self.assertIn("zip(cols, COMPARISON_SLOTS)", visible)
        self.assertIn("slot for slot in COMPARISON_SLOTS if slot in scripts", visible)
        self.assertIn('"Confronto orario", available_comparisons', visible)
        self.assertNotIn("zip(cols, SLOTS)", visible)
        self.assertNotIn('st.columns(3, gap="small")', visible)
        self.assertNotIn('list(scripts)', visible)
        self.assertNotIn('Pine 07:30, confronto',visible)
        self.assertIn("07:30", EXPLANATIONS["1550"])
        self.assertIn("15:50", EXPLANATIONS["2030"])

    def test_ndx_has_single_selected_snapshot_current_export(self):
        s=source("v2_market_engine.py")
        self.assertEqual(
            s.count('"Scarica Pine NET GAMMA corrente · NQ/MNQ (.pine)"'), 1)
        self.assertEqual(s.count('current_script = make_pine('), 1)
        self.assertIn('"0DTE": visual_profiles["0DTE"]', s)
        self.assertIn('"Weekly": visual_profiles["Weekly"]', s)
        self.assertIn('acquisition_time=st.session_state.get("ndx_capture_rome_iso")',s)
        self.assertIn("append_news(current_script, macro_news)", s)
        self.assertIn('with st.expander("Confronti orari · 07:30 → 15:50 / 15:50 → 20:30"',s)
        self.assertEqual(s.count('render_timed_pine_exports('), 1)
        self.assertLess(s.index('"Scarica Pine NET GAMMA corrente · NQ/MNQ (.pine)"'),
                        s.index('with st.expander("Confronti orari'))

    def test_etf_pine_current_export_is_unique_and_preserves_continuous(self):
        s=source("etf_pine_view.py")
        self.assertEqual(s.count('f"Scarica Pine NET GAMMA corrente · {label} (.pine)"'),1)
        self.assertEqual(s.count('script = make_etf_future_pine('),1)
        self.assertIn("continuous=True",s)
        self.assertNotIn("fetch_oil_pair",s)
        self.assertNotIn("prepare_locked_chart_mapping",s)
        self.assertIn("CONFRONTI" if False else "Confronti orari",s)
        self.assertEqual(s.count("render_timed_pine_exports("),1)
        self.assertLess(s.index('f"Scarica Pine NET GAMMA corrente'),
                        s.index('with st.expander("Confronti orari'))

    def test_no_code_generating_comparisons_is_changed_by_ui(self):
        # Separate the legacy pure generator and the new visible buttons.
        s=source("v2_pine_timed_exports.py")
        producer=s[s.index("def produce_timed_scripts("):
                   s.index("def render_timed_pine_exports(")]
        self.assertIn('if slot == "0730":',producer)
        self.assertIn('make_pine_comparison_v2(',producer)
        self.assertIn('prev_slot = "0730" if slot == "1550" else "1550"',producer)
        self.assertIn('scripts[slot] = script',producer)
        # The generated standalone 07:30 script is not a UI duplicate.
        view=s[s.index("def render_timed_pine_exports("):]
        self.assertIn("available_comparisons",view)
        self.assertIn('"Confronti non disponibili:',view)
        self.assertNotIn("for col, slot in zip(cols, SLOTS)",view)


if __name__ == "__main__":
    unittest.main()
