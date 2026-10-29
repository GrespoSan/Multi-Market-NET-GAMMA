"""No market connectivity required: verify exact 5-minute time matching."""
import unittest
from datetime import date, datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from future_ratio import (choose_contract, synchronized_pair, manual_pair,
                          fetch_pair)

DAY = date(2026, 10, 29)


def bars(*pairs):
    idx = pd.DatetimeIndex([t for t, _ in pairs], tz="UTC")
    return pd.DataFrame({"Close": [c for _, c in pairs]}, index=idx)


def t(hour, minute):
    return datetime(2026, 10, 29, hour, minute, tzinfo=timezone.utc)


class RatioTests(unittest.TestCase):
    def test_exact_timestamp_pair_and_lock_data(self):
        etf = bars((t(18, 0), 368.10), (t(18, 5), 368.36),
                   (t(18, 10), 368.50))
        fut = bars((t(18, 0), 4069.1), (t(18, 5), 4070.1),
                   (t(18, 15), 4080.0))
        result = synchronized_pair(
            etf, fut, "GLD", "GCZ26.CMX", "COMEX:GCZ2026",
            DAY, now=t(18, 20))
        self.assertEqual(result["bar_utc"], t(18, 5).isoformat(timespec="seconds"))
        self.assertEqual(result["etf_price"], 368.36)
        self.assertEqual(result["future_price"], 4070.1)
        self.assertAlmostEqual(result["ratio"], 4070.1/368.36)
        self.assertEqual(result["future_tv_symbol"], "COMEX:GCZ2026")

    def test_stale_bar_while_etf_open_rejected(self):
        a = bars((t(13, 35), 370.))
        b = bars((t(13, 35), 4050.))
        # 16:30 UTC = 12:30 NY, last common bar is almost 3 hours ago.
        with self.assertRaisesRegex(ValueError, "troppo vecchie"):
            synchronized_pair(a,b,"GLD","GCZ26.CMX","COMEX:GCZ2026",
                              DAY, now=t(16, 30))

    def test_unfinished_and_outside_regular_hours_rejected(self):
        a = bars((t(19, 55), 369.))
        b = bars((t(19, 55), 4100.))
        with self.assertRaisesRegex(ValueError, "Nessuna coppia"):
            synchronized_pair(a,b,"GLD","GCZ26.CMX","COMEX:GCZ2026",
                              DAY,now=t(19, 57))
        a = bars((t(20, 30), 369.))
        b = bars((t(20, 30), 4100.))
        with self.assertRaisesRegex(ValueError, "Nessuna coppia"):
            synchronized_pair(a,b,"GLD","GCZ26.CMX","COMEX:GCZ2026",
                              DAY,now=t(20, 50))

    def test_mismatched_timestamp_never_nearest_neighbor(self):
        etf = bars((t(18, 5), 368.36))
        fut = bars((t(18, 10), 4070.1))
        with self.assertRaisesRegex(ValueError, "Nessuna coppia"):
            synchronized_pair(etf,fut,"GLD","GCZ26.CMX","COMEX:GCZ2026",
                              DAY,now=t(18, 20))

    def test_invalid_or_na_prices_rejected(self):
        a = bars((t(18, 5), 0.0))
        b = bars((t(18, 5), 4070.1))
        with self.assertRaisesRegex(ValueError, "Nessuna coppia"):
            synchronized_pair(a,b,"GLD","GCZ26.CMX","COMEX:GCZ2026",
                              DAY,now=t(18, 20))

    def test_manual_pair_is_explicitly_unverified(self):
        pair = manual_pair(167.46, 101.14, "USO",
                           "CLZ26 · dicembre 2026", DAY, "14:45")
        self.assertAlmostEqual(pair["ratio"], 101.14/167.46)
        self.assertIn("NON verificata", pair["source"])
        self.assertEqual(pair["future_tv_symbol"], "NYMEX:CLZ2026")
        with self.assertRaises(ValueError):
            manual_pair(167.46,101.14,"USO",
                        "CLZ26 · dicembre 2026",DAY,"22:30")

    def test_chosen_contract_is_explicit(self):
        self.assertEqual(choose_contract("GLD", "GCZ26 · dicembre 2026"),
                         ("GCZ26.CMX", "COMEX:GCZ2026"))
        self.assertEqual(choose_contract("USO", "CLZ26 · dicembre 2026"),
                         ("CLZ26.NYM", "NYMEX:CLZ2026"))
        with self.assertRaisesRegex(ValueError, "Contratto"):
            choose_contract("USO","CL1!")

    def test_yfinance_never_silently_substitutes_continuous_future(self):
        class FakeTicker:
            def __init__(self, name):
                self.name = name
            def history(self, **kwargs):
                return bars((t(18, 0), 170. if self.name == "USO" else 101.))
        class FakeYahoo:
            used = []
            def Ticker(self, name):
                self.used.append(name)
                return FakeTicker(name)
        yahoo=FakeYahoo()
        pair=fetch_pair("USO", "CLZ26 · dicembre 2026",
                        DAY,now=t(18, 20),yf_module=yahoo)
        self.assertEqual(yahoo.used, ["USO", "CLZ26.NYM"])
        self.assertEqual(pair["future_tv_symbol"], "NYMEX:CLZ2026")


if __name__ == "__main__":
    unittest.main()
