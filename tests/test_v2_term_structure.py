"""Verified Massive first/second expiry selection and same-session settlements.

No live network; fake HTTP client checks 1 contracts + 2 aggs requests.
"""
import unittest
from datetime import date
from unittest.mock import Mock

from v2_term_structure import (
    select_first_two, settlement_for_session, compare_settlements,
    fetch_term_structure, CurveUnavailable,
)
from v2_volatility import same_spx_regime


def contract(ticker, maturity, product, venue="XCME"):
    return {
        "ticker": ticker, "product_code": product, "active": True,
        "type": "single", "first_trade_date": "2025-01-01",
        "last_trade_date": maturity, "trading_venue": venue,
    }


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self.data


class FakeClient:
    def __init__(self, contracts, bars):
        self.contracts, self.bars = contracts, bars
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if url.endswith("/contracts"):
            return FakeResponse({"status": "OK", "results": self.contracts})
        ticker = url.rsplit("/", 1)[-1]
        return FakeResponse({"status": "OK", "results": self.bars[ticker]})


def bar(ticker, day, settle):
    return {
        "ticker": ticker, "session_end_date": day,
        "settlement_price": settle,
        "close": 999999.0,  # never use trade close in curve calculation
    }


class FirstSecondExpiryTests(unittest.TestCase):
    def test_all_markets_select_nearest_two_by_last_trade_not_symbol(self):
        for product, contracts, expected in (
            ("NQ", [contract("NQH7", "2027-03-19", "NQ"),
                    contract("NQZ6", "2026-12-18", "NQ")],
             ("NQZ6", "NQH7")),
            ("GC", [contract("GCZ6", "2026-12-29", "GC", "XCEC"),
                    contract("GCX6", "2026-11-25", "GC", "XCEC")],
             ("GCX6", "GCZ6")),
            ("CL", [contract("CLF7", "2026-12-21", "CL", "XNYM"),
                    contract("CLZ6", "2026-11-20", "CL", "XNYM")],
             ("CLZ6", "CLF7")),
        ):
            with self.subTest(product=product):
                pair = select_first_two(contracts, product, date(2026, 10, 30))
                self.assertEqual(tuple(i["ticker"] for i in pair), expected)

    def test_expired_combo_inactive_and_other_product_are_not_selected(self):
        market = [
            contract("NQU6", "2026-09-18", "NQ"),
            contract("NQZ6-NQH7", "2026-12-18", "NQ"),
            {**contract("NQZ6", "2026-12-18", "NQ"), "active": False},
            contract("NQH7", "2027-03-19", "NQ"),
            contract("NQM7", "2027-06-17", "NQ"),
            contract("CLZ6", "2026-11-20", "CL"),
        ]
        self.assertEqual(
            [x["ticker"] for x in select_first_two(market, "NQ", date(2026, 10, 30))],
            ["NQH7", "NQM7"]
        )
        with self.assertRaises(CurveUnavailable):
            select_first_two(market[:3], "NQ", date(2026, 10, 30))

    def test_only_matching_session_and_settlement_is_accepted(self):
        self.assertEqual(settlement_for_session(
            {"status": "OK", "results": [
                bar("GCZ6", "2026-10-29", 4017.7),
                bar("GCZ6", "2026-10-30", 3898.9)]},
            "GCZ6", date(2026, 10, 30)), 3898.9)
        with self.assertRaises(CurveUnavailable):
            settlement_for_session({"status": "OK", "results": [
                bar("GCZ6", "2026-10-29", 4017.7)]},
                "GCZ6", date(2026, 10, 30))
        with self.assertRaises(CurveUnavailable):
            settlement_for_session({"status": "OK", "results": [
                bar("GCZ6", "2026-10-30", None)]},
                "GCZ6", date(2026, 10, 30))

    def test_term_curve_contango_backwardation_same_close_date(self):
        front, second = select_first_two([
            contract("CLF7", "2026-12-21", "CL"),
            contract("CLZ6", "2026-11-20", "CL")],
            "CL", date(2026, 10, 30))
        curve = compare_settlements(front, second, 104.12, 102.21,
                                    date(2026, 10, 30))
        self.assertEqual(curve["regime"], "BACKWARDATION")
        self.assertLess(curve["term_pct"], 0)
        self.assertEqual(same_spx_regime(curve["term_pct"], 0.5, False)["state"], "ALTA")
        forward = compare_settlements(front, second, 100.0, 101.0,
                                      date(2026, 10, 30))
        self.assertEqual(forward["regime"], "CONTANGO")
        self.assertEqual(same_spx_regime(forward["term_pct"], 0.5, False)["state"], "BASSA")

    def test_end_to_end_3_read_only_calls_and_no_secret_leak(self):
        contracts = [contract("NQH7", "2027-03-19", "NQ"),
                     contract("NQZ6", "2026-12-18", "NQ")]
        client = FakeClient(contracts, {
            "NQZ6": [bar("NQZ6", "2026-10-30", 28534.0)],
            "NQH7": [bar("NQH7", "2026-10-30", 28852.5)]
        })
        result = fetch_term_structure("NQ", date(2026, 10, 30),
                                      "private-key", requester=client)
        self.assertEqual(result["front"], "NQZ6")
        self.assertEqual(result["second"], "NQH7")
        self.assertEqual(result["regime"], "CONTANGO")
        self.assertEqual(len(client.calls), 3)
        self.assertEqual(client.calls[0][1]["params"]["date"], "2026-10-30")
        self.assertEqual(client.calls[0][1]["params"]["product_code"], "NQ")
        for url, kwargs in client.calls[1:]:
            self.assertEqual(kwargs["params"]["resolution"], "1session")
            self.assertIn("aggs/", url)
            self.assertEqual(kwargs["headers"]["Authorization"], "Bearer private-key")
        self.assertNotIn("private-key", str(result))

    def test_missing_api_key_never_issues_a_network_call(self):
        client = Mock()
        with self.assertRaises(CurveUnavailable):
            fetch_term_structure("GC", date(2026, 10, 30), "", requester=client)
        client.get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
