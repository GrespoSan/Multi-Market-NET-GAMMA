"""Massive one-contract session OHLC, no data from settlement or Yahoo."""
import unittest
from datetime import date
from unittest.mock import patch

from massive_futures_daily import (
    MassiveSourceError, previous_sessions, previous_daily_context,
    parse_session,
)


class Response:
    def __init__(self, bars):
        self._bars = bars
    def raise_for_status(self):
        pass
    def json(self):
        return {"status": "OK", "results": self._bars}


def raw(day, close, high, low, settle, ticker="CLZ6"):
    return {"ticker":ticker, "session_end_date":day, "close":close,
            "high":high, "low":low, "settlement_price":settle,
            "window_start": 1793059200000000000}


class MassiveDailyTests(unittest.TestCase):
    def test_cl_october_tradingview_vs_settlement_discrepancy(self):
        # Massive reported the close values independently of settlements:
        # +0.91% trade closes vs -0.76% settlement closes.
        data = [
            raw("2026-10-28",101.94,103.0,100.0,102.78),
            raw("2026-10-29",102.87,103.0,99.79,102.00),
            raw("2026-10-30",102.1,103.0,100.0,102.0),
        ]
        observed = {}
        def get(url, **kwargs):
            observed["url"] = url
            observed["params"] = kwargs["params"]
            observed["headers"] = kwargs["headers"]
            return Response(data)
        bars = previous_sessions("CLZ6", date(2026,10,30),
                                 "private-test-token", get=get)
        self.assertEqual(len(bars),2)
        self.assertEqual(bars[-1]["day"], date(2026,10,29))
        self.assertEqual(observed["params"]["resolution"], "1session")
        self.assertEqual(observed["url"].split("/")[-1], "CLZ6")
        self.assertIn("Bearer private-test-token",
                      observed["headers"]["Authorization"])
        result = previous_daily_context(bars)
        self.assertEqual(result["ticker"],"CLZ6")
        self.assertAlmostEqual(result["range_points"],3.21)
        self.assertAlmostEqual(result["range_pct"],3.21/102.87*100)
        self.assertAlmostEqual(result["change_pct"],(102.87/101.94-1)*100)
        self.assertGreater(result["change_pct"],0)
        # Settlement would be negative; must not use settlement_price.
        self.assertLess(102.0/102.78-1,0)
        self.assertEqual(result["previous_close_day"], "2026-10-28")

    def test_market_directions_same_date_all_four_futures(self):
        for ticker,c0,c1 in (
            ("ESZ6",7760.75,7710.25),("NQZ6",29756.25,29218.25),
            ("GCZ6",4081.20,4033.30),("CLZ6",101.94,102.87)):
            with self.subTest(ticker=ticker):
                bars=[parse_session(raw("2026-10-28",c0,c0+20,c0-10,0,ticker),ticker),
                      parse_session(raw("2026-10-29",c1,c1+20,c1-10,0,ticker),ticker)]
                result=previous_daily_context(bars)
                self.assertAlmostEqual(result["change_pct"],100*(c1/c0-1),places=5)

    def test_missing_key_or_invalid_ticker_never_requests(self):
        def no_network(*args,**kwargs):
            raise AssertionError("No network call expected")
        with self.assertRaisesRegex(MassiveSourceError,"MASSIVE_API_KEY"):
            previous_sessions("CLZ6",date(2026,10,30),"",get=no_network)
        with self.assertRaisesRegex(MassiveSourceError,"contratto reale"):
            previous_sessions("CL1!",date(2026,10,30),"SECRET",get=no_network)

    def test_avoid_cross_contract_daily_returns(self):
        before=parse_session(raw("2026-10-28",102,103,101,102,"CLZ6"),"CLZ6")
        after=parse_session(raw("2026-10-29",104,105,103,104,"CLF7"),"CLF7")
        with self.assertRaisesRegex(MassiveSourceError,"differenti"):
            previous_daily_context([before,after])

    def test_empty_or_incomplete_provider_returns_no_fabricated_numbers(self):
        with self.assertRaises(MassiveSourceError):
            previous_sessions("GCZ6",date(2026,10,30),"token",
                              get=lambda *a,**kw:Response([]))
        with self.assertRaises(MassiveSourceError):
            parse_session({"ticker":"ESZ6","session_end_date":"2026-10-29",
                           "close":100,"high":99,"low":98},"ESZ6")


if __name__=="__main__":
    unittest.main()
