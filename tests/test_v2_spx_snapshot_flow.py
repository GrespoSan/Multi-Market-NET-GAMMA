"""SPX-like NET GAMMA snapshot selection without a Supabase dependency.

All fixtures are synthetic. Never calls Cboe or external APIs.
"""
import unittest
from datetime import datetime, timezone
from pathlib import Path

from v2_storage_off import _archive_label, SLOTS, AVAILABLE_MARKETS

ROOT = Path(__file__).resolve().parent.parent


class SPXSnapshotParityTests(unittest.TestCase):
    def test_display_provenance_is_real_created_at_converted_to_rome(self):
        item={"name":"v2-multi-market-42","created_at":"2026-10-30T13:55:00Z"}
        label=_archive_label(item)
        self.assertIn("30/10/2026 · 14:55 Roma", label)
        self.assertIn("v2-multi-market-42", label)
        self.assertEqual(SLOTS["0730"],"Mattina 07:30 Roma")
        self.assertEqual(SLOTS["1550"],"Pomeriggio 08:50 Chicago")
        self.assertEqual(SLOTS["2030"],"Sera 13:30 Chicago")
        self.assertEqual(AVAILABLE_MARKETS,("NDX","GLD","USO"))

    def test_same_archive_selector_and_manual_override_for_all_markets(self):
        accessor=(ROOT/"v2_storage_off.py").read_text(encoding="utf-8")
        self.assertIn("Snapshot originale opzioni · archivio automatico", accessor)
        self.assertIn("options[1] if len(options) > 1 else", accessor)
        self.assertIn("def prefer_manual_source(symbol):", accessor)
        self.assertIn("if chosen == \"manuale\":", accessor)
        self.assertIn("fetch_artifact_snapshot", accessor)
        self.assertIn("v2_archive_capture_nyday_", accessor)
        self.assertNotIn("st.session_state.get(\"v2_role\") != \"admin\"",accessor)
        self.assertNotIn("from storage import Store",accessor)
        for file,symbol in (
            ("v2_market_engine.py","NDX"),
            ("gld_cboe_view.py","GLD"),
            ("uso_cboe_view.py","USO")):
            source=(ROOT/file).read_text()
            with self.subTest(symbol=symbol):
                self.assertIn(f"prefer_manual_source('{symbol}')" if symbol=="NDX"
                              else f'prefer_manual_source("{symbol}")',source)
                self.assertIn("archive_panel",source)
                self.assertIn("v2_archive_capture_nyday_",source)
                self.assertIn("v2_archive_capture_rome_",source)
                self.assertIn("independent_scale",source)
        header=(ROOT/"app.py").read_text()
        self.assertIn('st.header("NET GAMMA · formula Serafini")',header)
        self.assertIn("60%/23%",header)
        self.assertNotIn("from storage import",header)

    def test_scheduler_retains_chicago_dst_and_authorized_source_gate(self):
        from v2_schedule import SLOTS as clock
        import v2_cron
        self.assertEqual(clock["07:30"][0],"Europe/Rome")
        self.assertEqual(clock["15:50"][0],"America/Chicago")
        self.assertEqual(clock["20:30"][0],"America/Chicago")
        self.assertIn("V2_AUTHORIZED_FEED_CONFIRMED",Path(v2_cron.__file__).read_text())
        self.assertIn("V2_FEED_TOKEN",Path(v2_cron.__file__).read_text())
        self.assertIn("V2_ARCHIVE_FERNET_KEY",Path(v2_cron.__file__).read_text())
        self.assertIn("delayed_quotes",Path(v2_cron.__file__).read_text())

if __name__=="__main__":
    unittest.main()
