"""V2 calendar: 07:30 Rome, 08:50 + 10:00 Chicago, historical 20:30."""
import unittest
from datetime import datetime, date, timezone

from v2_schedule import decision
from v2_pine_session import slots_for_day, parse_archived_capture, compare_capture_pair


class Capture1700Tests(unittest.TestCase):
    def test_winter_10_chicago_external_slot_1700(self):
        capture = decision(
            datetime(2026, 11, 12, 16, 2, tzinfo=timezone.utc),
            requested="17:00", external=True)
        self.assertTrue(capture["run"])
        self.assertEqual(capture["slot"], "17:00")
        self.assertEqual(capture["time_zone"], "America/Chicago")
        self.assertEqual(capture["scheduled_local"][11:16], "10:00")
        self.assertEqual(capture["chicago"].strftime("%H:%M"), "10:02")
        self.assertEqual(capture["rome"].strftime("%H:%M"), "17:02")

    def test_summer_10_chicago_external_slot_1700(self):
        capture = decision(
            datetime(2027, 7, 12, 15, 2, tzinfo=timezone.utc),
            requested="17:00", external=True)
        self.assertTrue(capture["run"])
        self.assertEqual(capture["time_zone"], "America/Chicago")
        self.assertEqual(capture["chicago"].strftime("%H:%M"), "10:02")
        self.assertEqual(capture["rome"].strftime("%H:%M"), "17:02")

    def test_dst_mismatch_10_chicago_means_16_rome(self):
        # US summer time begins three weeks before Europe in March.
        capture = decision(
            datetime(2027, 3, 15, 15, 2, tzinfo=timezone.utc),
            requested="17:00", external=True)
        self.assertTrue(capture["run"])
        self.assertEqual(capture["chicago"].strftime("%H:%M"), "10:02")
        self.assertEqual(capture["rome"].strftime("%H:%M"), "16:02")
        too_early = decision(
            datetime(2027, 3, 15, 14, 57, tzinfo=timezone.utc),
            requested="17:00", external=True)
        self.assertFalse(too_early["run"])

    def test_0730_rome_and_1550_chicago_not_changed(self):
        rome = decision(
            datetime(2026, 11, 12, 6, 31, tzinfo=timezone.utc),
            requested="07:30", external=True)
        self.assertTrue(rome["run"])
        self.assertEqual(rome["time_zone"], "Europe/Rome")
        chicago = decision(
            datetime(2026, 11, 12, 14, 51, tzinfo=timezone.utc),
            requested="15:50", external=True)
        self.assertTrue(chicago["run"])
        self.assertEqual(chicago["time_zone"], "America/Chicago")
        self.assertEqual(chicago["scheduled_local"][11:16], "08:50")

    def test_1550_chicago_also_moves_to_1450_rome_in_mismatch(self):
        capture = decision(
            datetime(2027, 3, 15, 13, 51, tzinfo=timezone.utc),
            requested="15:50", external=True)
        self.assertTrue(capture["run"])
        self.assertEqual(capture["chicago"].strftime("%H:%M"), "08:51")
        self.assertEqual(capture["rome"].strftime("%H:%M"), "14:51")

    def test_native_github_cron_disabled(self):
        with self.assertRaisesRegex(ValueError, "Cron GitHub disabilitato"):
            decision(datetime(2026, 11, 12, 16, 2, tzinfo=timezone.utc),
                     event_cron="0 16 * * 1-5")

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
