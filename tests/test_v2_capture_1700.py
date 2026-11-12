"""Regressioni calendario V2: 17:00 Rome e archivi storici 20:30."""
import unittest
from datetime import datetime, date, timezone

from v2_schedule import decision
from v2_pine_session import slots_for_day, parse_archived_capture, compare_capture_pair


class Capture1700Tests(unittest.TestCase):
    def test_winter_cron_only_16_utc(self):
        correct = decision(datetime(2026, 11, 12, 16, 2, tzinfo=timezone.utc),
                           event_cron="0 16 * * 1-5")
        self.assertTrue(correct["run"])
        self.assertEqual(correct["slot"], "17:00")
        wrong = decision(datetime(2026, 11, 12, 15, 2, tzinfo=timezone.utc),
                         event_cron="0 15 * * 1-5")
        self.assertFalse(wrong["run"])
        self.assertEqual(wrong["reason"], "DST_NON_CORRISPONDENTE")

    def test_summer_cron_only_15_utc(self):
        correct = decision(datetime(2027, 7, 12, 15, 2, tzinfo=timezone.utc),
                           event_cron="0 15 * * 1-5")
        self.assertTrue(correct["run"])
        self.assertEqual(correct["slot"], "17:00")
        wrong = decision(datetime(2027, 7, 12, 16, 2, tzinfo=timezone.utc),
                         event_cron="0 16 * * 1-5")
        self.assertFalse(wrong["run"])

    def test_stale_cron_job_is_not_captured(self):
        skipped = decision(datetime(2026, 11, 12, 19, 31, tzinfo=timezone.utc),
                           requested="20:30", external=True)
        self.assertFalse(skipped["run"])
        self.assertEqual(skipped["reason"], "SLOT_2030_DISMESSO")

    def test_historic_and_new_slots(self):
        self.assertEqual(slots_for_day(date(2026, 11, 11)),
                         ("0730", "1550", "2030"))
        self.assertEqual(slots_for_day(date(2026, 11, 12)),
                         ("0730", "1550", "1700"))

    def test_filenames_accepted_for_all_markets(self):
        for symbol in ("NDX", "RUT", "DJX", "GLD", "USO"):
            new = parse_archived_capture(
                f"{symbol}_20261112T160100Z_1700_aaaaaaaaaaaa.json.gz",
                symbol, date(2026, 11, 12))
            self.assertEqual(new["slot"], "1700")
            old = parse_archived_capture(
                f"{symbol}_20261111T193000Z_2030_aaaaaaaaaaaa.json.gz",
                symbol, date(2026, 11, 11))
            self.assertEqual(old["slot"], "2030")

    def test_chronological_comparisons(self):
        symbol = "NDX"
        p = parse_archived_capture(
            f"{symbol}_20261112T145100Z_1550_aaaaaaaaaaaa.json.gz",
            symbol, date(2026, 11, 12))
        n = parse_archived_capture(
            f"{symbol}_20261112T160100Z_1700_bbbbbbbbbbbb.json.gz",
            symbol, date(2026, 11, 12))
        self.assertTrue(compare_capture_pair(p, n, "1550", "1700"))


if __name__ == "__main__":
    unittest.main()
