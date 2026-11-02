"""DST-safe acquisition clocks in every Multi-Market TradingView Pine export.

Synthetic market data only; no GitHub/Cboe/Massive/Yahoo requests.
"""
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from etf_future_pine import make_etf_future_pine
from pine_export import make_pine
from v2_pine_capture import pine_capture_clock


def etf_group(exp, strike):
    return {"expiry":exp.isoformat(), "usable":True,
            "rows":[{"strike":float(strike), "net":2.5},
                    {"strike":float(strike)+1, "net":-1.25}]}


def etf_mapping(symbol):
    etf = 168.0 if symbol == "USO" else 368.0
    fut = 101.0 if symbol == "USO" else 4070.0
    return {"etf_symbol":symbol, "etf_price":etf, "future_price":fut,
            "ratio":fut/etf, "bar_ny":"2026-10-30T15:55:00-04:00",
            "future_tv_symbol":("NYMEX:CLZ2026" if symbol == "USO"
                                else "COMEX:GCZ2026"),
            "source":"Synthetic 5m same-time pair"}


def ndx_group(exp, strike=25500.0):
    return {"expiry":exp.isoformat(), "band_pct":3.0,
            "rows":[{"strike_index":float(strike), "net_gamma":0.1}]}


class AcquisitionClockTests(unittest.TestCase):
    def test_winter_and_summer_labels_use_real_rome_timezone(self):
        winter=pine_capture_clock("2026-11-02T14:50:00Z")
        self.assertEqual(winter["stamp"],"02/11/2026 15:50 CET")
        summer=pine_capture_clock("2026-07-06T13:50:00+00:00")
        self.assertEqual(summer["stamp"],"06/07/2026 15:50 CEST")

    def test_march_dst_jumps_and_october_repeated_hour(self):
        # EU spring forward: Rome jumps 01:59 CET to 03:00 CEST.
        before=pine_capture_clock("2026-03-29T00:30:00Z")
        after=pine_capture_clock("2026-03-29T01:30:00Z")
        self.assertEqual(before["clock"],"01:30 CET")
        self.assertEqual(after["clock"],"03:30 CEST")
        # EU fall back: repeated 02:30 has two distinguishable UTC instants.
        first=pine_capture_clock("2026-10-25T00:30:00Z")
        second=pine_capture_clock("2026-10-25T01:30:00Z")
        self.assertEqual(first["clock"],"02:30 CEST")
        self.assertEqual(second["clock"],"02:30 CET")
        self.assertNotEqual(first["stamp"],second["stamp"])

    def test_us_eu_dst_non_aligned_week_uses_rome_not_chicago_offset(self):
        # US DST still active Oct 26, EU already on standard time Oct 25.
        clock=pine_capture_clock("2026-10-26T14:50:00Z")
        self.assertEqual(clock["clock"],"15:50 CET")

    def test_source_timestamp_is_never_assumed_utc(self):
        for raw in (None, "", "2026-11-02T14:50:00",
                    "02/11/2026", "fuso non dichiarato",
                    "25/10/2026 02:30:00 Roma"):
            with self.subTest(raw=raw):
                clock=pine_capture_clock(raw)
                self.assertFalse(clock["verified"])
                self.assertIn("non verificata",clock["stamp"])
        # Legacy direct NDX acquisition human-readable Rome wall time:
        self.assertEqual(
            pine_capture_clock("02/11/2026 15:50:03 Roma")["clock"],
            "15:50 CET")

    def test_ndx_pine_title_and_both_gamma_headings(self):
        day=date(2026,11,2)
        profiles={"0DTE":ndx_group(day),
                  "Weekly":ndx_group(date(2026,11,6),25600)}
        result=make_pine(profiles,140.0,day,"0DTE + Weekly",
                         acquisition_time="2026-11-02T14:50:00Z")
        self.assertIn(
            'indicator("Multi-Market NET GAMMA · NDX/NQ · 2026-11-02 · '
            'Acq 15:50 CET · 0DTE + Weekly"',result)
        self.assertIn('"0DTE 02/11 · Acq 15:50 CET"',result)
        self.assertIn('"Weekly 06/11 · Acq 15:50 CET"',result)
        self.assertIn("02/11/2026 15:50 CET",result)
        self.assertIn("140.0",result)
        self.assertIn("0.1",result)

    def test_gold_oil_pine_titles_and_labels_use_same_clock(self):
        day=date(2026,11,2)
        for etf,strike in (("GLD",368),("USO",168)):
            with self.subTest(etf=etf):
                profiles={"0DTE":etf_group(day,strike),
                          "Weekly":etf_group(date(2026,11,6),strike+3)}
                source=etf_mapping(etf)
                script=make_etf_future_pine(
                    etf,profiles,float(strike),day,"0DTE + Weekly",source,
                    acquisition_time="2026-11-02T14:50:00+00:00")
                self.assertIn("Acq 15:50 CET",script)
                self.assertIn(
                    '"0DTE 02/11 · Acq 15:50 CET"',script)
                self.assertIn(
                    '"Weekly 06/11 · Acq 15:50 CET"',script)
                self.assertIn(
                    "// Ora acquisizione fotografia Cboe (Europe/Rome; CET/CEST): "
                    "02/11/2026 15:50 CET",script)
                self.assertIn("Gamma originale",script)
                self.assertIn("mapETF(",script)
                self.assertIn("2.5",script)

    def test_unverified_import_does_not_invent_clock(self):
        day=date(2026,11,2)
        for etf,strike in (("GLD",368),("USO",168)):
            with self.subTest(etf=etf):
                script=make_etf_future_pine(
                    etf,{"0DTE":etf_group(day,strike)},float(strike),
                    day,"Solo 0DTE",etf_mapping(etf))
                self.assertIn("ora acquisizione non verificata",script)
                self.assertNotIn("Acq 15:50 CET",script)
        ndx=make_pine({"0DTE":ndx_group(day)},140.0,day,
                      "Solo 0DTE")
        self.assertIn("ora acquisizione non verificata",ndx)

    def test_repositories_pass_the_actual_capture_to_exporters(self):
        root=Path(__file__).resolve().parents[1]
        ndx=(root/"v2_market_engine.py").read_text()
        etf=(root/"etf_pine_view.py").read_text()
        self.assertIn("ndx_capture_rome_iso",ndx)
        self.assertIn("v2_archive_capture_rome_NDX",ndx)
        self.assertIn("render_timed_pine_exports(",ndx)
        self.assertIn("render_timed_pine_exports(",etf)
        timed=(root/"v2_pine_timed_exports.py").read_text()
        self.assertIn('acquisition_time=now["capture"]["rome"]',timed)
        self.assertIn('make_pine_comparison_v2(',timed)


if __name__=="__main__":
    unittest.main()
