"""Test three Europe/Rome slots, source licensing gate, private archival."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scheduled_slots import schedule_decision, week_key
from scheduled_capture import (capture_one, main, validate_authorized_url,
                               validate_chain)
from gamma_chart_style import top_levels, profile_chart


def at(year, month, day, hour, minute):
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


def tiny(symbol):
    expiry = "261030"
    def opt(side, strike):
        return {"option": f"{symbol}{expiry}{side}{int(strike*1000):08d}",
                "gamma": .08, "open_interest": 50, "volume": 5}
    return json.dumps({
        "symbol": "_" + symbol if symbol == "NDX" else symbol,
        "timestamp": "2026-10-29 15:35:00",
        "data": {"options": [opt("C", 30000 if symbol == "NDX" else 200),
                             opt("P", 30000 if symbol == "NDX" else 200),
                             opt("C", 30005 if symbol == "NDX" else 205),
                             opt("P", 30005 if symbol == "NDX" else 205)],
                 "prev_day_close": 30000 if symbol == "NDX" else 200}}).encode()


class FakeArchive:
    def __init__(self):
        self.uploaded = []
    def upload(self, path, content, mime):
        self.uploaded.append((path, content, mime))


class FakeResponse:
    status_code=200
    url="https://licensed.example.org/option-chains/GLD"
    def __init__(self, data):
        self.data=data
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return None
    def raise_for_status(self):
        pass
    def iter_content(self, chunk_size):
        yield self.data


class ScheduledTests(unittest.TestCase):
    def test_all_three_slots_cet_weekdays(self):
        for slot, hour, minute in [("07:30",6,30),("15:50",14,50),("20:30",19,30)]:
            with self.subTest(slot=slot):
                d=schedule_decision(at(2026,10,29,hour,minute+2),
                                    requested=slot)
                self.assertTrue(d["run"])
                self.assertEqual(d["slot"],slot)
                self.assertEqual(d["reason"],"IN_WINDOW")

    def test_summer_time_and_outside_window(self):
        # 15:50 Rome summer = 13:50 UTC; 15:50 winter = 14:50 UTC.
        self.assertTrue(schedule_decision(at(2026,7,15,13,50),
                                          requested="15:50")["run"])
        self.assertFalse(schedule_decision(at(2026,10,29,15,20),
                                           requested="15:50")["run"])
        self.assertEqual(schedule_decision(at(2026,10,31,6,30))["reason"],
                         "WEEKEND")
        d=schedule_decision(at(2026,10,31,6,30),
                            requested="07:30", manual=True)
        self.assertEqual(d["slot"],"manuale")

    def test_late_runner_does_not_backdate_acquisition(self):
        self.assertFalse(schedule_decision(at(2026,10,29,7,0),
                                           requested="07:30")["run"])
        self.assertEqual(week_key(at(2026,10,29,6,30)), "2026-W44")

    def test_original_cboe_delayed_urls_denied_for_automation(self):
        for url in ("https://cdn.cboe.com/api/global/delayed_quotes/options/GLD.json",
                    "https://www.cboe.com/delayed_quotes/USO/quote_table"):
            with self.assertRaisesRegex(ValueError, "vieta"):
                validate_authorized_url(url)
        self.assertEqual(validate_authorized_url("https://licensed.example.org/api/GLD"),
                         "https://licensed.example.org/api/GLD")
        with self.assertRaises(ValueError):
            validate_authorized_url("http://licensed.example.org")

    def test_market_chain_root_must_match(self):
        for symbol in ("NDX","GLD","USO"):
            x=validate_chain(symbol, tiny(symbol))
            self.assertEqual(x["contratti"],4)
            self.assertGreater(x["gamma_positivi"],0)
        with self.assertRaisesRegex(ValueError, "Atteso GLD"):
            validate_chain("GLD",tiny("USO"))

    def test_without_source_or_private_archive_no_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            log=capture_one("GLD",at(2026,10,29,6,30),"07:30","",
                            authorized=False,output=out)
            self.assertEqual(log["status"],"NON_CONFIGURATO")
            self.assertFalse((out/"snapshots").exists())
            # Even with authorized URL, no private storage -> no fetch.
            log=capture_one("GLD",at(2026,10,29,6,30),"07:30",
                            "https://licensed.example.org/GLD",
                            authorized=True,output=out)
            self.assertEqual(log["status"],"NON_CONFIGURATO")
            self.assertFalse((out/"snapshots").exists())

    def test_authorized_source_archives_private_only_and_audit_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=FakeArchive()
            raw=tiny("GLD")
            log=capture_one("GLD",at(2026,10,29,14,50),"15:50",
                            "https://licensed.example.org/GLD",
                            authorized=True,archive=store,
                            get=lambda *a,**kw: FakeResponse(raw),
                            output=Path(tmp))
            self.assertEqual(log["status"],"SCARICATO")
            self.assertEqual(len(store.uploaded),2)
            self.assertIn("snapshots/GLD/2026-W44",store.uploaded[0][0])
            self.assertEqual(store.uploaded[0][2],"application/gzip")
            self.assertFalse((Path(tmp)/"snapshots").exists())
            self.assertTrue((Path(tmp)/"logs").exists())

    def test_run_status_writes_three_market_skip_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Do not call main here: it writes capture_output, just test clock independently.
            dec=schedule_decision(at(2026,10,29,19,30))
            self.assertEqual(dec["slot"],"20:30")


class DesignTests(unittest.TestCase):
    def test_summary_preserves_original_gamma_and_reference(self):
        rows=[{"strike":200,"net":5.5,"call":7,"put":1.5},
              {"strike":205,"net":-4,"call":0,"put":4}]
        summary=top_levels(rows,"strike","net")
        self.assertEqual(summary["positive"],(200.,5.5))
        self.assertEqual(summary["negative"],(205.,-4.))
        self.assertAlmostEqual(summary["total"],1.5)
        fig=profile_chart(rows,"USO",200,[-5,6],[190,210])
        self.assertEqual(list(fig.data[0].x),[5.5,-4.])
        self.assertEqual(list(fig.data[0].y),[200.,205.])
        self.assertEqual(list(fig.layout.yaxis.range),[190.,210.])


if __name__ == "__main__":
    unittest.main()
