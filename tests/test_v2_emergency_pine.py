"""One-photo emergency V2 Pine for NQ/GC/CL; offline, synthetic Cboe only."""
import copy
import gzip
import json
import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

from v2_emergency_pine import build_current_pine, _current_trading_day, _source_near_session

DAY = date(2026, 11, 4)
WEEK = date(2026, 11, 6)


def photo(symbol):
    base = {"NDX": 25500, "GLD": 368, "USO": 168}[symbol]
    opts = []
    step = 10 if symbol == "NDX" else 1
    for expiry in (DAY, WEEK):
        for strike in (base-step, base, base+step):
            for kind in ("C", "P"):
                opts.append({
                    "option": f"{symbol}{expiry:%y%m%d}{kind}{strike*1000:08d}",
                    "gamma": 0.012 if kind == "C" else 0.01,
                    "open_interest": 40 if kind == "C" else 20,
                    "volume": 4,
                })
    return {
        "symbol": symbol, "timestamp": "2026-11-04 13:30:00",
        "data": {"prev_day_close": base, "current_price": base+2, "options": opts},
    }


def mapping(symbol):
    etf = 368.0 if symbol == "GLD" else 168.0
    fut = 4060.0 if symbol == "GLD" else 80.0
    return {
        "etf_symbol": symbol, "etf_price": etf, "future_price": fut,
        "ratio": fut / etf,
        "future_tv_symbol": "COMEX:GCZ2026" if symbol == "GLD" else "NYMEX:CLZ2026",
        "bar_ny": "2026-11-04T09:45:00-05:00",
        "source": "Synthetic synchronized quotes",
    }


def original(symbol):
    return json.dumps(photo(symbol)).encode()


class EmergencyTests(unittest.TestCase):
    def test_three_market_one_photo_export(self):
        for symbol in ("NDX", "GLD", "USO"):
            with self.subTest(symbol=symbol):
                raw = original(symbol)
                conversion = 125.0 if symbol == "NDX" else mapping(symbol)
                result = build_current_pine(
                    symbol, raw, DAY, photo(symbol)["data"]["prev_day_close"],
                    conversion, capture_time="2026-11-04T15:50:00+01:00")
                script = result["pine"]
                self.assertTrue(script.startswith("//@version=6\nindicator("))
                self.assertEqual(script.count("indicator("), 1)
                self.assertIn("EMERGENZA CORRENTE", script)
                self.assertEqual(set(result["profiles"]), {"0DTE", "Weekly"})
                self.assertEqual(result["expiry_weekly"], WEEK)
                self.assertEqual(result["symbol"], symbol)
                self.assertEqual(len(result["profiles"]["0DTE"]["rows"]), 3)
                self.assertEqual(len(result["profiles"]["Weekly"]["rows"]), 3)
                self.assertEqual(raw, original(symbol))  # no mutation
                if symbol == "NDX":
                    self.assertIn("syminfo.root == \"MNQ\"", script)
                    self.assertIn("25625", script)
                    self.assertNotIn("mapETF(", script)
                else:
                    self.assertIn("mapETF(", script)
                    self.assertIn("Bloccato", script)
                    self.assertIn("Gamma", script)

    def test_gzip_keeps_original_parser_rules(self):
        raw = gzip.compress(original("GLD"))
        result = build_current_pine("GLD", raw, DAY, 368., mapping("GLD"))
        self.assertIn("GLD", result["pine"])

    def test_old_source_rejected_without_false_current_label(self):
        old = photo("USO")
        old["timestamp"] = "2026-10-30 20:30:00"
        with self.assertRaisesRegex(ValueError, "troppo distante"):
            build_current_pine("USO", json.dumps(old).encode(), DAY,
                               168., mapping("USO"))
        self.assertEqual(_source_near_session("2026-11-03 23:50:00", DAY),
                         date(2026, 11, 3))

    def test_different_market_and_missing_expiries_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "Atteso GLD"):
            build_current_pine("GLD", original("USO"), DAY, 368., mapping("GLD"))
        d = photo("NDX")
        d["data"]["options"] = [o for o in d["data"]["options"] if "261104" not in o["option"]]
        with self.assertRaisesRegex(ValueError, "0DTE"):
            build_current_pine("NDX", json.dumps(d).encode(), DAY, 25500., 125.)
        d2 = photo("GLD")
        d2["data"]["options"] = [o for o in d2["data"]["options"] if "261106" not in o["option"]]
        with self.assertRaisesRegex(ValueError, "Weekly"):
            build_current_pine("GLD", json.dumps(d2).encode(), DAY, 368., mapping("GLD"))

    def test_no_implicit_futures_conversion(self):
        with self.assertRaisesRegex(ValueError, "Rapporto ETF/future"):
            build_current_pine("USO", original("USO"), DAY, 168., None)
        with self.assertRaisesRegex(ValueError, "altro strumento"):
            build_current_pine("USO", original("USO"), DAY, 168., mapping("GLD"))
        with self.assertRaisesRegex(ValueError, "Differenziale"):
            build_current_pine("NDX", original("NDX"), DAY, 25500., None)

    def test_new_york_overnight_session_and_weekend(self):
        tz = ZoneInfo("America/New_York")
        self.assertEqual(_current_trading_day(datetime(2026,11,3,17,0,tzinfo=tz)),
                         date(2026,11,3))
        self.assertEqual(_current_trading_day(datetime(2026,11,3,18,0,tzinfo=tz)),DAY)
        self.assertEqual(_current_trading_day(datetime(2026,11,6,19,0,tzinfo=tz)),
                         date(2026,11,9))


if __name__=="__main__":
    unittest.main()
