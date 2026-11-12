"""Six-market unified Pine / official SPX bridge regression tests.

All fixtures are synthetic; they do not claim a live Supabase connection or
TradingView compilation. SPX source remains an independent read-only archive.
"""
import gzip
import json
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from v2_spx_bridge import _select_logs, _weekly_expiry, spx_record
from v2_unified_pine import MARKETS, ROOTS, build_unified_pine
from v2_unified_timed import build_unified_comparison_pine

DAY = date(2026, 11, 12)
FRIDAY = date(2026, 11, 13)
ROOT = Path(__file__).resolve().parents[1]


def fixture_archive(hour):
    options = []
    for expiry in (DAY, FRIDAY):
        for offset in list(range(-25, 0)) + list(range(1, 26)):
            strike = 6000 + offset
            for right, gamma in (("C", 0.02), ("P", 0.01)):
                code = (
                    f"SPXW{expiry:%y%m%d}{right}"
                    f"{int(round(strike * 1000)):08d}"
                )
                options.append({
                    "option": code, "gamma": gamma,
                    "open_interest": 100, "volume": 0,
                })
    snap = {"symbol": "_SPX", "data": {
        "options": options, "prev_day_close": 6000.0,
        "current_price": 6000.0,
    }}
    return {
        "snapshot": snap,
        "download_rome": f"2026-11-12T{hour}:02:00+01:00",
        "origin": "SPX UFFICIALE",
        "log": "2026-W46/snapshots/SPX_CBOE_20261112_000000.json.gz",
    }


class SPXUnifiedTests(unittest.TestCase):
    def test_spx_and_es_mes_are_sixth_market(self):
        self.assertEqual(len(MARKETS), 6)
        self.assertIn("SPX", MARKETS)
        self.assertEqual(ROOTS["SPX"], ("ES", "MES"))
        source = (ROOT / "v2_unified_pine.py").read_text()
        self.assertIn('syminfo.root == "ES" or syminfo.root == "MES"', source)
        self.assertIn('string activeMarket = isES ? "SPX"', source)

    def test_official_profiles_25_below_25_above_same_formula(self):
        rec = spx_record(fixture_archive("07:31"), DAY, 38.0, extension=False)
        self.assertEqual(len(rec["main"]), 50)
        self.assertEqual(len(rec["weekly"]), 50)
        self.assertEqual(rec["main_expiry"], DAY)
        self.assertEqual(rec["weekly_expiry"], FRIDAY)
        self.assertEqual(rec["main"][0]["strike_spx"], 5975)
        self.assertEqual(rec["main"][-1]["strike_spx"], 6025)
        self.assertNotIn(6000.0, [x["strike_spx"] for x in rec["main"]])
        self.assertTrue(all(x["net_gamma"] == 1.0 for x in rec["main"]))
        self.assertEqual(rec["basis"], 38.0)
        self.assertEqual(rec["captured"]["clock"], "07:31 CET")

    def test_pine_0730_contains_sixth_market_not_a_fake_recalculation(self):
        rec = spx_record(fixture_archive("07:31"), DAY, 38.0, extension=True)
        code = build_unified_pine(DAY, {"SPX": rec})
        self.assertIn("var array<float> SPXLevels", code)
        self.assertIn("var array<float> SPXWeekGamma", code)
        self.assertIn("var array<float> SPXCalls", code)
        self.assertIn('    "SPX" => 38.0', code)
        self.assertIn('"SPX" => SPXLevels', code)
        self.assertIn('"SPX" => SPXWeekLevels', code)
        self.assertIn('indicator("Serafini Multi-Market · UNICO 07:30', code)
        self.assertIn('string activeMarket = isES ? "SPX"', code)

    def test_pine_1550_and_1700_compare_real_spx_originals(self):
        prev = spx_record(fixture_archive("07:31"), DAY, 38.0)
        cur1550 = spx_record(fixture_archive("15:51"), DAY, 38.0)
        cur1700 = spx_record(fixture_archive("17:01"), DAY, 38.0)
        for slot, current, prior, prior_label in (
            ("1550", cur1550, prev, "07:30"),
            ("1700", cur1700, cur1550, "15:50"),
        ):
            with self.subTest(slot=slot):
                code = build_unified_comparison_pine(
                    DAY, {"SPX": current}, {"SPX": prior}, slot)
                self.assertIn("var array<float> SPXPrevLevels", code)
                self.assertIn('showPrevious = input.bool(false', code)
                self.assertIn(f"{prior_label} · precedente", code)
                self.assertIn('renderProfile(drawMain', code)
                self.assertIn('renderProfile(drawWeek', code)
                self.assertIn('"SPX" => SPXGamma', code)
                self.assertEqual(code.count('indicator("'), 1)

    def test_missing_previous_keeps_spx_current_plus_weekly(self):
        current = spx_record(fixture_archive("15:51"), DAY, 38)
        code = build_unified_comparison_pine(DAY, {"SPX": current},
                                             {}, "1550")
        self.assertIn("var array<float> SPXPrevLevels = array.new_float()", code)
        self.assertIn("bool haveData = array.size(mainLevels) > 0", code)

    def test_validated_original_spx_log_ids_and_not_lookahead(self):
        base = {
            "rome_date": DAY.isoformat(), "status": "NUOVO",
            "file": "2026-W46/snapshots/SPX_CBOE_20261112_000000.json.gz",
        }
        logs = [
            dict(base, scheduled_slot="30 7 * * 1-5",
                 download_rome="2026-11-12T07:31:00+01:00"),
            dict(base, scheduled_slot="50 15 * * 1-5",
                 download_rome="2026-11-12T15:52:00+01:00"),
            dict(base, scheduled_slot="0 17 * * 1-5",
                 download_rome="2026-11-12T17:02:00+01:00"),
            dict(base, scheduled_slot="30 20 * * 1-5",
                 download_rome="2026-11-12T20:31:00+01:00"),
            dict(base, scheduled_slot="0 17 * * 1-5",
                 download_rome="2026-11-13T17:02:00+01:00"),
            dict(base, scheduled_slot="0 17 * * 1-5",
                 status="ERRORE", download_rome="2026-11-12T17:03:00+01:00"),
        ]
        result = _select_logs(logs, DAY, ("0730", "1550", "1700"))
        self.assertEqual(len(result["0730"]), 1)
        self.assertEqual(len(result["1550"]), 1)
        self.assertEqual(len(result["1700"]), 1)
        self.assertEqual(_weekly_expiry(DAY), FRIDAY)

    def test_only_multimarket_reads_spx_no_remote_modifications(self):
        bridge = (ROOT / "v2_spx_bridge.py").read_text()
        self.assertIn('"GET"', bridge)
        self.assertIn('"POST"', bridge)  # Storage list, NOT upload
        self.assertNotIn('"/object/" +', bridge)
        self.assertNotIn('method="PUT"', bridge)
        self.assertNotIn("def upload(", bridge)
        self.assertNotIn("def delete(", bridge)
        timed = (ROOT / "v2_unified_timed.py").read_text()
        self.assertIn('load_official_spx(day, slots_for_day(day))', timed)
        self.assertIn('spx_record(current_frame, day, basis', timed)
        self.assertIn('ES/MES', timed)


if __name__ == "__main__":
    unittest.main()
