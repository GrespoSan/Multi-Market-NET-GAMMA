"""RUT/DJX Streamlit widget lifetime regression.

When switching between markets Streamlit removes the text_input key, but a
verified or edited basis should survive in an independent state key.
"""
import ast
import unittest
from pathlib import Path

VIEW = Path(__file__).resolve().parents[1] / "v2_index_market_view.py"


class BasisPersistenceTests(unittest.TestCase):
    def test_persist_independent_from_widget(self):
        text = VIEW.read_text(encoding="utf-8")
        ast.parse(text)
        self.assertIn('saved_key = f"{prefix}_basis_saved"', text)
        self.assertIn('st.session_state[saved_key] = verified_text', text)
        self.assertIn('if value_key not in st.session_state:', text)
        self.assertIn('st.session_state[value_key] = st.session_state[saved_key]', text)
        self.assertIn('st.session_state[saved_key] = st.session_state.get(value_key, "")', text)
        self.assertIn('key=value_key, on_change=_basis_edited', text)

    def test_day_change_invalidates_basis(self):
        text = VIEW.read_text(encoding="utf-8")
        self.assertIn('if st.session_state.get(target_key) != day.isoformat():', text)
        self.assertIn('st.session_state.pop(saved_key, None)', text)
        self.assertIn('st.session_state.pop(result_key, None)', text)

    def test_weekly_saved_independently_of_widget_lifecycle(self):
        text = VIEW.read_text(encoding="utf-8")
        self.assertIn('weekly_saved_key = f"{prefix}_weekly_saved"', text)
        self.assertIn("elif weekly_key not in st.session_state:", text)
        self.assertIn("weekly_saved_key, preferred_weekly", text)
        self.assertIn('st.session_state[weekly_saved_key] = st.session_state[weekly_key]', text)
        self.assertIn("key=weekly_key, on_change=_weekly_edited", text)

    def test_weekly_refreshes_on_snapshot_date_close_or_band_change(self):
        text = VIEW.read_text(encoding="utf-8")
        self.assertIn('weekly_context = (snapshot_digest, day, float(close), float(band))', text)
        self.assertIn('st.session_state[weekly_saved_key] = preferred_weekly', text)
        self.assertIn("if st.session_state[weekly_key] not in allowed_weeklies:", text)

    def test_default_band_5_percent_for_both(self):
        text = VIEW.read_text(encoding="utf-8")
        self.assertIn('min_value=0.5, max_value=25.0, value=5.0, step=0.5', text)
        self.assertIn('prefix = f"v2_primary_{ticker.lower()}"', text)
        self.assertIn('key=f"{prefix}_band"', text)


if __name__ == "__main__":
    unittest.main()
