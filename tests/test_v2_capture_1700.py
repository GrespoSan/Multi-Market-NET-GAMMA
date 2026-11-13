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

    def test_old_1700_not_active_after_16_nov(self):
        capture = decision(
            datetime(2027, 7, 12, 15, 2, tzinfo=timezone.utc),
            requested="17:00", external=True)
        self.assertFalse(capture["run"])
        self.assertEqual(capture["reason"], "SLOT_STORICO_O_NON_ANCORA_ATTIVO")

    def test_new_0916_1046_chicago_winter_and_dst_mismatch(self):
        for day, utc_0916, utc_1046, rome_0916, rome_1046 in (
            (date(2026, 11, 16), (2026,11,16,15,16), (2026,11,16,16,46),
             "16:16", "17:46"),
            (date(2027, 3, 15), (2027,3,15,14,16), (2027,3,15,15,46),
             "15:16", "16:46"),
            (date(2027, 10, 28), (2027,10,28,14,16), (2027,10,28,15,46),
             "15:16", "16:46"),
        ):
            with self.subTest(day=day):
                for requested, when, chicago, roma in (
                    ("16:16", utc_0916, "09:16", rome_0916),
                    ("17:46", utc_1046, "10:46", rome_1046)):
                    result = decision(datetime(*when, tzinfo=timezone.utc),
                                      requested=requested, external=True)
                    self.assertTrue(result["run"], result)
                    self.assertEqual(result["slot"], requested)
                    self.assertEqual(result["time_zone"], "America/Chicago")
                    self.assertEqual(result["chicago"].strftime("%H:%M"), chicago)
                    self.assertEqual(result["rome"].strftime("%H:%M"), roma)

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

    def test_old_1550_rejected_post_cutover(self):
        capture = decision(
            datetime(2027, 3, 15, 13, 51, tzinfo=timezone.utc),
            requested="15:50", external=True)
        self.assertFalse(capture["run"])
        self.assertEqual(capture["reason"], "SLOT_STORICO_O_NON_ANCORA_ATTIVO")

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
        self.assertEqual(slots_for_day(date(2026, 11, 16)),
                         ("0730", "1616", "1746"))

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

    def test_new_cboe_archive_names_and_chronology(self):
        first = parse_archived_capture(
            "NDX_20261116T151700Z_1616_aaaaaaaaaaaa.json.gz",
            "NDX", date(2026, 11, 16))
        last = parse_archived_capture(
            "NDX_20261116T164700Z_1746_bbbbbbbbbbbb.json.gz",
            "NDX", date(2026, 11, 16))
        self.assertTrue(compare_capture_pair(first, last, "1616", "1746"))
        self.assertLess(first["utc"], last["utc"])

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
