"""Free official macro calendar regression tests, no paid FinanceCalendar API."""
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
import macro_calendar
import macro_events


DAY = date(2026, 11, 12)
EVENT = {"day": DAY, "clock": "14:30", "kind": "Jobless Claims",
         "status": "scheduled", "priority": "ALTA",
         "provider": "FRED / DOL", "source": "https://fred.stlouisfed.org/"}


class V2FreeMacroCalendarTests(unittest.TestCase):
    def test_paid_calendar_removed_from_live_modules(self):
        root = Path(__file__).resolve().parents[1]
        for path in ("macro_calendar.py", "macro_events.py"):
            code = (root / path).read_text(encoding="utf-8").lower()
            self.assertNotIn("financecalendar.com", code)
            self.assertNotIn("finance_calendar_api_key", code)

    def test_official_free_sources_available(self):
        self.assertEqual(
            set(macro_calendar.SOURCES),
            {"BLS", "BEA", "Census", "Fed", "ISM", "Jobless Claims"})

    def test_pine_reuses_same_calendar_and_rome_time(self):
        with patch("macro_events.load_calendar",
                   return_value=([EVENT], {"healthy": ["Jobless Claims"]})):
            output = macro_events.events_for_pine(DAY)
        self.assertEqual(output, [EVENT])

    def test_pine_rejects_unverified_clock_and_other_day(self):
        incomplete = [
            dict(EVENT, clock="Orario da verificare"),
            dict(EVENT, day=date(2026, 11, 13)),
            dict(EVENT),
        ]
        with patch("macro_events.load_calendar",
                   return_value=(incomplete, {})):
            self.assertEqual(macro_events.events_for_pine(DAY), [EVENT])

    def test_blS_still_available_when_other_providers_fail(self):
        with patch("bls_calendar.fetch_bls", return_value=[EVENT]), \
             patch("macro_calendar._bea_events", side_effect=OSError()), \
             patch("macro_calendar._census_events", side_effect=OSError()), \
             patch("macro_calendar._fed_events", side_effect=OSError()), \
             patch("macro_calendar._ism_events", side_effect=OSError()), \
             patch("macro_calendar._claims_events", side_effect=OSError()):
            events, state = macro_calendar.load_calendar.__wrapped__(DAY, DAY)
        self.assertEqual(events, [EVENT])
        self.assertIn("BLS", state["healthy"])
        self.assertFalse(state["complete"])


if __name__ == "__main__":
    unittest.main()
