"""V2 FinanceCalendar API-key regression for context and Pine exports.

No real FinanceCalendar or Streamlit credentials needed.
"""
import json
import unittest
from datetime import date
from unittest.mock import patch

import macro_calendar
import macro_events


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, size):
        return json.dumps({
            "events": [{
                "date": "2026-11-02",
                "series_code": "us-cpi",
                "series_name": "US CPI",
                "time_utc": "2026-11-02T13:30:00Z",
                "country": "US",
                "status": "scheduled",
            }],
            "total": 1,
        }).encode("utf-8")


class V2FinanceCalendarTests(unittest.TestCase):
    def setUp(self):
        macro_calendar._fetch.clear()
        macro_events._fetch.clear()

    def test_both_sources_send_key_in_header_only(self):
        for module in (macro_calendar, macro_events):
            with self.subTest(module=module.__name__), patch.object(
                    module, "urlopen", return_value=FakeResponse()) as mock_open:
                rows = module._fetch("2026-11-02", "2026-11-09",
                                     "mock-secret-key-not-real")
                self.assertEqual(len(rows), 1)
                request = mock_open.call_args.args[0]
                self.assertIn("country=US", request.full_url)
                self.assertNotIn("mock-secret-key-not-real", request.full_url)
                headers = {name.lower(): value for name, value
                           in request.header_items()}
                self.assertEqual(headers["x-api-key"], "mock-secret-key-not-real")

    def test_missing_key_does_not_call_financecalendar(self):
        for module in (macro_calendar, macro_events):
            with self.subTest(module=module.__name__), patch.object(
                    module, "urlopen") as mock_open:
                with self.assertRaisesRegex(ValueError, "Chiave FinanceCalendar mancante"):
                    module._fetch("2026-11-02", "2026-11-09", "")
                mock_open.assert_not_called()

    def test_pine_uses_same_dual_source_calendar_and_secret_as_dashboard(self):
        with patch.object(macro_calendar.st, "secrets",
                          {"FINANCE_CALENDAR_API_KEY": "synthetic-private-key"}), \
             patch.object(macro_calendar, "urlopen", return_value=FakeResponse()) as mock_open, \
             patch("bls_calendar.fetch_bls", return_value=[]):
            result = macro_events.events_for_pine(date(2026, 11, 2))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["kind"], "CPI")
        self.assertEqual(result[0]["clock"], "14:30")
        request = mock_open.call_args.args[0]
        self.assertEqual({k.lower(): v for k, v in request.header_items()}["x-api-key"],
                         "synthetic-private-key")

    def test_pine_keeps_bls_cpi_even_without_financecalendar(self):
        event = {
            "day": date(2026, 11, 2), "clock": "14:30", "kind": "CPI",
            "priority": "ALTA", "source": "https://www.bls.gov/schedule/news_release/cpi.htm",
            "provider": "BLS", "official_schedule": True,
        }
        with patch.object(macro_calendar.st, "secrets", {}), \
             patch("bls_calendar.fetch_bls", return_value=[event]):
            result = macro_events.events_for_pine(date(2026, 11, 2))
        self.assertEqual(result, [event])


if __name__ == "__main__":
    unittest.main()
