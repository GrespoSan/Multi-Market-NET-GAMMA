"""ES-only Edge GEX Wall/Flip in all three Multi-Market UNICO Pine exports.

Synthetic snapshots; tests never request live Cboe, Supabase or Edge ZIP.
"""
import hashlib
import unittest
from datetime import date
from unittest.mock import patch

from v2_spx_bridge import _edge_levels_for_same_spx, spx_record
from v2_unified_pine import build_unified_pine, MARKETS
from v2_unified_timed import build_unified_comparison_pine

DAY = date(2026, 11, 12)
FRIDAY = date(2026, 11, 13)
SHA = hashlib.sha256(b"original-gz-cboe").hexdigest()


def official_snapshot(clock="07:31"):
    options = []
    for expiry in (DAY, FRIDAY):
        for gap in list(range(-25, 0)) + list(range(1, 26)):
            strike = 6000 + gap
            for kind, gamma in (("C", .02), ("P", .01)):
                code = f"SPXW{expiry:%y%m%d}{kind}{int(round(strike*1000)):08d}"
                options.append({
                    "option": code, "gamma": gamma,
                    "open_interest": 100, "volume": 0,
                })
    return {
        "snapshot": {"symbol": "_SPX", "data": {
            "options": options, "current_price": 6000.0,
            "prev_day_close": 6000.0,
        }},
        "download_rome": f"2026-11-12T{clock}:02:00+01:00",
        "origin": "SPX UFFICIALE",
        "raw": b"original-gz-cboe",
        "source_sha256": SHA,
    }


def edge_result(call=6015., put=5980., flip=6002., *, sufficient=True,
                sha=SHA, expiries=None):
    return {
        "symbol": "SPX", "mode": "0DTE",
        "expiries": expiries or [DAY.isoformat()],
        "quality_sufficient": sufficient,
        "sha256": sha, "spot_spx": 6000.,
        "call_wall_spx": call, "put_wall_spx": put, "gamma_flip_spx": flip,
    }


def record(clock, edge=None):
    with patch("edge_auto.result_from_snapshot",
               return_value=edge_result() if edge is None else edge):
        return spx_record(official_snapshot(clock), DAY, 38.0, extension=False)


class UnifiedEsGexTests(unittest.TestCase):
    def test_exact_source_and_model_quality_are_required(self):
        archive = official_snapshot()
        with patch("edge_auto.result_from_snapshot",
                   return_value=edge_result()):
            levels = _edge_levels_for_same_spx(archive, DAY, 6000.0, 38.0)
        self.assertEqual(levels, {
            "call_wall_spx": 6015., "put_wall_spx": 5980.,
            "gamma_flip_spx": 6002.,
        })
        for wrong in (
            edge_result(sufficient=False),
            edge_result(sha="0" * 64),
            edge_result(expiries=["2026-11-13"]),
            {**edge_result(), "spot_spx": 6010.},
        ):
            with self.subTest(wrong=wrong):
                with patch("edge_auto.result_from_snapshot", return_value=wrong):
                    self.assertIsNone(
                        _edge_levels_for_same_spx(archive, DAY, 6000., 38.))
        self.assertIsNone(_edge_levels_for_same_spx(
            {**archive, "raw": None}, DAY, 6000., 38.))

    def test_real_edge_cloud_feed_fallback_requires_same_slot_and_sha(self):
        from v2_spx_bridge import _cached_verified_official_feed
        from gex_official_csv import verified_official_gex_csv
        raw = b"original-gz-cboe"
        metadata = {
            "schema":"serafini_mt4_v4", "mode":"Ufficiale",
            "date_rome":DAY.isoformat(), "slot_rome":"17:00",
            "download_clock_rome":"17:00:18",
            "gex_model":"EDGE_0DTE", "gex_expiry":DAY.isoformat(),
            "gex_source_sha256":hashlib.sha256(raw).hexdigest(),
            "gex_cboe_timestamp":"official timestamp",
            "gex_call_wall_spx":"6015",
            "gex_put_wall_spx":"5980",
            "gex_gamma_flip_spx":"6002",
        }
        content = (chr(10).join(f"{k},{v}" for k,v in metadata.items())
                   + chr(10) + "profile,expiry,strike_spx,price_es,net_gamma"
                   + chr(10)).encode()
        archive = {
            "raw":raw, "source_sha256":hashlib.sha256(raw).hexdigest(),
            "snapshot":{"timestamp":"official timestamp"},
            "download_rome":f"{DAY.isoformat()}T17:00:18+01:00",
            "slot_rome":"1700",
        }
        with patch("edge_auto.result_from_snapshot",
                   return_value=edge_result(sufficient=False)), patch(
                "v2_spx_bridge._secrets",
                return_value=("https://example.invalid","token","spx-snapshots")), patch(
                "v2_spx_bridge._cached_verified_official_feed",
                return_value=content):
            value = _edge_levels_for_same_spx(archive, DAY, 6000., 38.)
            self.assertEqual(value, {
                "call_wall_spx":6015., "put_wall_spx":5980.,
                "gamma_flip_spx":6002.})
            self.assertIsNone(_edge_levels_for_same_spx(
                {**archive, "slot_rome":"1550"}, DAY, 6000., 38.))
            self.assertIsNone(_edge_levels_for_same_spx(
                {**archive, "source_sha256":"bad"}, DAY, 6000., 38.))
        self.assertIsNone(verified_official_gex_csv(
            content, b"other-gz", DAY, "1700",
            "official timestamp", "17:00:18"))

    def test_ui_cache_is_versioned_for_new_gex_lines(self):
        from pathlib import Path
        text = (Path(__file__).resolve().parents[1] /
                "v2_unified_timed.py").read_text(encoding="utf-8")
        self.assertIn("mm_unified_prepared_by_slot_gex_source_v2", text)
        self.assertNotIn('cache_key = "mm_unified_prepared_by_slot"', text)

    def test_0730_es_lines_and_independent_styles(self):
        current = record("07:31")
        pine = build_unified_pine(DAY, {"SPX": current})
        self.assertIn("float gexCallES = 6053.00000000", pine)
        self.assertIn("float gexPutES = 6018.00000000", pine)
        self.assertIn("float gexFlipES = 6040.00000000", pine)
        self.assertIn('if isES and showGexLevels', pine)
        self.assertIn('syminfo.root == "MES"', pine)
        self.assertIn("line.style_dotted, width=gexFlipWidth", pine)
        self.assertEqual(pine.count("showGexLevels = input.bool"), 1)
        for x in ("gexCallColor", "gexPutColor", "gexFlipColor"):
            self.assertEqual(pine.count(x + " = input.color"), 1)
        for x in ("gexCallWidth", "gexPutWidth", "gexFlipWidth"):
            self.assertEqual(pine.count(x + " = input.int"), 1)
        for sym in MARKETS:
            self.assertIn("var array<float> " + sym + "Levels", pine)

    def test_comparisons_use_current_gex_not_preceding(self):
        previous = record("07:31", edge_result(6030., 5950., 6050.))
        now = record("15:51", edge_result(6015., 5980., 6002.))
        then = record("17:01", edge_result(6040., 5960., 6001.))
        for slot, current, prior, expected, not_expected in (
            ("1550", now, previous, "6053.00000000", "6068.00000000"),
            ("1700", then, now, "6078.00000000", "6053.00000000"),
        ):
            with self.subTest(slot=slot):
                script = build_unified_comparison_pine(
                    DAY, {"SPX": current}, {"SPX": prior}, slot)
                self.assertIn("float gexCallES = " + expected, script)
                self.assertNotIn("float gexCallES = " + not_expected, script)
                self.assertEqual(script.count("showGexLevels = input.bool"), 1)
                self.assertIn("if isES and showGexLevels", script)
                self.assertEqual(script.count("if barstate.islast and validTicker"), 1)
                self.assertIn("showPrevious = input.bool", script)

    def test_unavailable_flip_or_missing_spx_does_not_borrow_levels(self):
        no_flip = record("15:51", edge_result(flip=None))
        pine = build_unified_pine(DAY, {"SPX": no_flip})
        self.assertIn("float gexCallES = 6053.00000000", pine)
        self.assertIn("float gexFlipES = na", pine)
        empty = build_unified_pine(DAY, {"NDX": None})
        self.assertIn("float gexCallES = na", empty)
        self.assertIn("float gexPutES = na", empty)
        self.assertIn("float gexFlipES = na", empty)
        self.assertIn("if isES and showGexLevels", empty)

    def test_bridge_is_read_only_and_other_pines_are_untouched(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        bridge = (root / "v2_spx_bridge.py").read_text()
        single = (root / "v2_unified_pine.py").read_text()
        timed = (root / "v2_unified_timed.py").read_text()
        self.assertIn('"raw": raw', bridge)
        self.assertIn('if digest != archive.get("source_sha256"):', bridge)
        self.assertIn('append_es_gex_overlays(', single)
        self.assertIn('append_es_gex_overlays(', timed)
        self.assertNotIn('method="PUT"', bridge)


if __name__ == "__main__":
    unittest.main()
