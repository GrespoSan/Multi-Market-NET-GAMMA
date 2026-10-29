"""Unit tests for GLD mode; use synthetic fixtures only, never synthetic live levels."""
import unittest
from datetime import date

from gld_alpaca import calculate_profile, next_friday, fetch_gld


def chain():
    contracts = []
    snapshots = {}
    for strike in (365, 366, 367):
        for side, code in (("call", "C"), ("put", "P")):
            symbol = f"GLD261030{code}{strike * 1000:08d}"
            contracts.append({"symbol": symbol, "underlying_symbol": "GLD",
                              "expiration_date": "2026-10-30", "status": "active",
                              "strike_price": str(strike), "type": side,
                              "open_interest": "10" if side == "call" else "5",
                              "open_interest_date": "2026-10-27", "multiplier": "100"})
            snapshots[symbol] = {"greeks": {"gamma": 0.1 if side == "call" else 0.2},
                                 "dailyBar": {"v": 3 if side == "call" else 1}}
    return {"expiry": "2026-10-30", "contracts": contracts, "snapshots": snapshots}


class GldEngineTests(unittest.TestCase):
    def test_next_friday_excludes_today_on_friday(self):
        self.assertEqual(next_friday(date(2026, 10, 29)), date(2026, 10, 30))
        self.assertEqual(next_friday(date(2026, 10, 30)), date(2026, 11, 6))

    def test_real_contract_arithmetic_and_pairs(self):
        result = calculate_profile(chain(), 364, 368)
        self.assertTrue(result["usable"])
        self.assertEqual(result["eligible"], 6)
        self.assertEqual(result["complete_strikes"], 3)
        self.assertAlmostEqual(result["rows"][0]["call"], 1.3)
        self.assertAlmostEqual(result["rows"][0]["put"], 1.2)
        self.assertAlmostEqual(result["rows"][0]["net"], 0.1)
        self.assertEqual(result["oi_dates"], ["2026-10-27"])

    def test_missing_greek_excludes_pair(self):
        fixture = chain()
        del fixture["snapshots"]["GLD261030C00365000"]["greeks"]
        result = calculate_profile(fixture, 364, 368)
        self.assertEqual(result["complete_strikes"], 2)
        self.assertEqual(result["missing"]["gamma"], 1)
        self.assertEqual(result["missing"]["lato_incompleto"], 1)
        self.assertNotIn(365, [r["strike"] for r in result["rows"]])

    def test_missing_oi_never_replaced_by_zero(self):
        fixture = chain()
        for contract in fixture["contracts"]:
            if contract["type"] == "put":
                contract["open_interest"] = None
        result = calculate_profile(fixture, 364, 368)
        self.assertFalse(result["usable"])
        self.assertEqual(result["rows"], [])
        self.assertEqual(result["missing"]["OI"], 3)

    def test_invalid_multiplier_rejected(self):
        fixture = chain()
        fixture["contracts"][0]["multiplier"] = "10"
        result = calculate_profile(fixture, 364, 368)
        self.assertEqual(result["missing"]["multiplier"], 1)
        self.assertNotIn(365, [r["strike"] for r in result["rows"]])

    def test_no_live_expiry_does_not_create_data(self):
        result = calculate_profile({"expiry": "2026-10-29", "contracts": [],
                                    "snapshots": {}}, 364, 368)
        self.assertFalse(result["usable"])
        self.assertEqual(result["rows"], [])


if __name__ == "__main__":
    unittest.main()
