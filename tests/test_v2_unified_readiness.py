"""Readiness of all 6 scheduled unified Pine exports.

At 16:57 Rome the 17:00 snapshot is not due; after 17:00 a missing
source must never generate a Pine that falsely calls itself six-market.
"""
from datetime import date, datetime
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from zoneinfo import ZoneInfo

from v2_unified_pine import MARKETS
from v2_unified_timed import (
    _slot_has_occurred,
    _missing_unified_markets,
    prepare_slot,
)


ROME = ZoneInfo("Europe/Rome")
NY = ZoneInfo("America/New_York")
DAY = date(2026, 11, 12)


class UnifiedReadinessTests(TestCase):
    def test_17_snapshot_not_available_at_1657(self):
        at_1657 = datetime(2026, 11, 12, 16, 57, tzinfo=ROME)
        self.assertTrue(_slot_has_occurred(DAY, "0730", at_1657))
        self.assertTrue(_slot_has_occurred(DAY, "1550", at_1657))
        self.assertFalse(_slot_has_occurred(DAY, "1700", at_1657))

    def test_17_snapshot_becomes_due_after_1700(self):
        at_1701 = datetime(2026, 11, 12, 17, 1, tzinfo=ROME)
        self.assertTrue(_slot_has_occurred(DAY, "1700", at_1701))
        self.assertFalse(_slot_has_occurred(date(2026, 11, 13), "1700", at_1701))

    def test_1550_chicago_respects_timezone(self):
        at_rome_1545 = datetime(2026, 11, 12, 15, 45, tzinfo=ROME)
        at_rome_1555 = datetime(2026, 11, 12, 15, 55, tzinfo=ROME)
        self.assertFalse(_slot_has_occurred(DAY, "1550", at_rome_1545))
        self.assertTrue(_slot_has_occurred(DAY, "1550", at_rome_1555))

    def test_missing_five_markets_is_not_six_market_export(self):
        self.assertEqual(len(MARKETS), 6)
        missing = _missing_unified_markets(
            {"SPX": {"main": [1], "weekly": [2]}},
            {"SPX": "OK · SPX UFFICIALE"})
        self.assertEqual(missing, ["NDX", "RUT", "DJX", "GLD", "USO"])

    def test_all_six_required_with_verified_status(self):
        data = {symbol: object() for symbol in MARKETS}
        good = {symbol: "OK · 17:00" for symbol in MARKETS}
        self.assertEqual(_missing_unified_markets(data, good), [])
        good["NDX"] = "N/D · file mancante"
        self.assertEqual(_missing_unified_markets(data, good), ["NDX"])

    def test_missing_capture_reports_each_original_market(self):
        with patch("v2_spx_bridge.load_official_spx", return_value={}), \
             patch("v2_unified_timed.load_pine_slot_captures", return_value={}):
            records, previous, reports = prepare_slot(DAY, "1700")
        self.assertEqual(records, {})
        self.assertEqual(previous, {})
        self.assertEqual(set(reports), set(MARKETS))
        self.assertTrue(all(reports[m].startswith("N/D") for m in MARKETS))

    def test_ui_cannot_download_partial_pine_and_auto_refreshes(self):
        source = (Path(__file__).resolve().parents[1] /
                  "v2_unified_timed.py").read_text(encoding="utf-8")
        self.assertIn('if not _slot_has_occurred(day, slot):', source)
        self.assertIn('missing = _missing_unified_markets(current, reports)', source)
        self.assertIn('if not missing:', source)
        self.assertIn('if prepared is None or stale_incomplete:', source)
        self.assertIn('run_every=180', source)
        self.assertNotIn('if current else None', source)
        self.assertIn('st.button(f"Pine · {label} · non disponibile"', source)


if __name__ == "__main__":
    import unittest
    unittest.main()
