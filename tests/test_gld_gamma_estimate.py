"""Deterministic tests for an *estimated* 0DTE GLD gamma, not real market data."""
from datetime import datetime, timezone
import unittest

from gld_gamma_estimate import (
    bs_price_gamma, estimate_0dte, infer_iv_from_mid,
)


NOW = "2026-10-29T16:00:00Z"  # noon New York, open trading session
RATE = 0.035
SPOT = 368.0
TAU = (4 * 60 + 15) / (365 * 24 * 60)  # 12:00 -> 16:15 NY


def snapshot_fixture():
    contracts = []
    snap = {}
    later_contracts = []
    later_snapshots = {}
    for strike in (367, 368, 369):
        for side, cp in (("call", "C"), ("put", "P")):
            sym = f"GLD261029{cp}{strike * 1000:08d}"
            weekly = f"GLD261030{cp}{strike * 1000:08d}"
            contract = {"symbol": sym, "underlying_symbol": "GLD",
                        "expiration_date": "2026-10-29", "status": "active",
                        "type": side, "strike_price": str(strike),
                        "multiplier": "100", "open_interest": "300",
                        "open_interest_date": "2026-10-27"}
            wcontract = dict(contract)
            wcontract["symbol"] = weekly
            wcontract["expiration_date"] = "2026-10-30"
            contracts.append(contract)
            later_contracts.append(wcontract)
            price, _ = bs_price_gamma(SPOT, strike, RATE, TAU, .27, side)
            snap[sym] = {"latestQuote": {"t": NOW, "bp": max(price-.01, .01),
                                        "ap": price+.01},
                         "dailyBar": {"t": "2026-10-29T04:00:00Z", "v": 42}}
            later_snapshots[weekly] = {"impliedVolatility": .28,
                                       "latestQuote": {"t": NOW, "bp": .5, "ap": .6}}
    return {"prev_close": 368.0, "band_pct": 1.0, "captured_at": "2026-10-29T16:00:15+00:00",
            "spot_quote": {"t": NOW, "bp": 367.99, "ap": 368.01},
            "groups": {"0DTE": {"expiry": "2026-10-29", "contracts": contracts, "snapshots": snap},
                       "Weekly": {"expiry": "2026-10-30", "contracts": later_contracts,
                                  "snapshots": later_snapshots}}}


class GammaEstimateTests(unittest.TestCase):
    def test_infer_iv_recovers_model_value(self):
        p, g = bs_price_gamma(SPOT, 368, RATE, TAU, .27, "call")
        iv = infer_iv_from_mid(SPOT, 368, RATE, TAU, "call", p-.01, p+.01)
        self.assertIsNotNone(iv)
        self.assertAlmostEqual(iv, .27, places=5)
        self.assertGreater(g, 0)

    def test_estimated_0dte_matched_strikes(self):
        r = estimate_0dte(snapshot_fixture(), annual_rate=RATE, use_weekly_proxy=False)
        self.assertTrue(r["usable"])
        self.assertEqual(r["valid_contracts"], 6)
        self.assertEqual(r["complete_strikes"], 3)
        self.assertEqual(r["sources"], {"0DTE mid": 6})
        self.assertTrue(all(x["call_gamma"] > 0 and x["put_gamma"] > 0 for x in r["rows"]))
        self.assertEqual(r["oi_dates"], ["2026-10-27"])

    def test_missing_bid_ask_falls_back_to_weekly_iv_only_if_permitted(self):
        d = snapshot_fixture()
        sym = "GLD261029C00368000"
        d["groups"]["0DTE"]["snapshots"][sym]["latestQuote"]["bp"] = .0
        r = estimate_0dte(d, annual_rate=RATE, use_weekly_proxy=True)
        self.assertTrue(r["usable"])
        self.assertEqual(r["sources"]["Weekly IV proxy"], 1)
        self.assertEqual([x for x in r["rows"] if x["strike"] == 368][0]["call_method"],
                         "Weekly IV proxy")
        r2 = estimate_0dte(d, annual_rate=RATE, use_weekly_proxy=False)
        self.assertFalse(r2["usable"])  # coverage 5/6 but two complete pairs only
        self.assertEqual(r2["complete_strikes"], 2)

    def test_out_of_session_rejects_all(self):
        d = snapshot_fixture()
        d["spot_quote"]["t"] = "2026-10-29T21:00:00Z"
        d["captured_at"] = "2026-10-29T21:00:10+00:00"
        r = estimate_0dte(d)
        self.assertFalse(r["usable"])
        self.assertIn("out_of_session", r["excluded"])

    def test_stale_option_quotes_rejected(self):
        d = snapshot_fixture()
        for s in d["groups"]["0DTE"]["snapshots"].values():
            s["latestQuote"]["t"] = "2026-10-29T14:00:00Z"
        r = estimate_0dte(d, use_weekly_proxy=True)
        self.assertFalse(r["usable"])
        self.assertEqual(r["valid_contracts"], 0)
        self.assertEqual(r["excluded"]["stale_or_missing_option_quote"], 6)

    def test_no_oi_never_defaults_zero(self):
        d = snapshot_fixture()
        for c in d["groups"]["0DTE"]["contracts"]:
            c["open_interest"] = None
        r = estimate_0dte(d)
        self.assertFalse(r["usable"])
        self.assertEqual(r["valid_contracts"], 0)

    def test_wide_quote_rejected_without_proxy(self):
        d = snapshot_fixture()
        for s in d["groups"]["0DTE"]["snapshots"].values():
            s["latestQuote"].update(bp=.01, ap=2.0)
        r = estimate_0dte(d, use_weekly_proxy=False)
        self.assertFalse(r["usable"])

    def test_expiry_15_min_guard(self):
        d = snapshot_fixture()
        d["spot_quote"]["t"] = "2026-10-29T20:05:01Z"
        d["captured_at"] = "2026-10-29T20:05:10+00:00"
        r = estimate_0dte(d)
        self.assertFalse(r["usable"])
        self.assertIn("less_than_15_min_to_close", r["excluded"])


if __name__ == "__main__":
    unittest.main()
