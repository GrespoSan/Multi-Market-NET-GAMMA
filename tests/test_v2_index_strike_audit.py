"""Forensic CBOE strike audit: no new Gamma and no silent exclusions.

The synthetic fixtures exercise filtering; real option-chain completeness
must still be checked using the UI's original CBOE snapshot.
"""
import unittest
from datetime import date
from v2_index_strike_audit import audit_strikes
from v2_universal_cboe import profile

DAY = date(2026, 11, 11)


def contract(root, side, strike, *, gamma=0.1, oi=30, volume=5, day=DAY):
    return {
        "option": f"{root}{day:%y%m%d}{side}{round(strike*1000):08d}",
        "gamma": gamma, "open_interest": oi, "volume": volume,
    }


class StrikeAuditTests(unittest.TestCase):
    def fixture(self, ticker="DJX"):
        weekly_root = ticker + "W"
        base = 520 if ticker == "DJX" else 2800
        options = []
        # Two genuine paired strikes: one combines main and weekly roots.
        for strike in (base, base + 1):
            for root, side in ((ticker, "C"), (weekly_root, "P")):
                options.append(contract(root, side, strike))
        # One-sided: contract genuinely absent from this snapshot.
        options.append(contract(ticker, "C", base + 2))
        # One-sided with present but invalid gamma on other side.
        options.append(contract(weekly_root, "C", base + 3))
        options.append(contract(weekly_root, "P", base + 3, gamma=None))
        # Repeated OCC contract, excluded rather than double counted.
        options.append(dict(options[0]))
        # Out of band, and different expiry, not eligible to plot.
        options.append(contract(ticker, "C", base * 1.20))
        options.append(contract(ticker, "P", base + 1, day=date(2026, 11, 13)))
        return {
            "symbol": "_" + ticker,
            "timestamp": "2026-11-11 14:00:00",
            "data": {"options": options, "prev_day_close": float(base)}
        }, base

    def test_reconcile_djx_and_rut_and_keep_original_gamma(self):
        for ticker, factor in (("DJX", 100.), ("RUT", 1.)):
            with self.subTest(ticker=ticker):
                doc, ref = self.fixture(ticker)
                audit = audit_strikes(doc, ticker, DAY, ref, band=10.,
                                       factor=factor, basis=23.)
                m = audit["metrics"]
                self.assertEqual(m["raw_records"], 10)
                self.assertEqual(m["selected_expiry_contracts"], 9)
                self.assertEqual(m["outside_band_contracts"], 1)
                self.assertEqual(m["in_band_contracts"], 8)
                self.assertEqual(m["duplicate_occ"], 1)
                self.assertEqual(m["valid_contracts"], 6)
                self.assertEqual(m["incomplete_greeks_oi_volume"], 1)
                self.assertEqual(m["COPPIA_VALIDA"], 2)
                self.assertEqual(m["UN_SOLO_LATO_PRESENTE"], 1)
                self.assertEqual(m["ALTRO_LATO_INCOMPLETO"], 1)
                self.assertEqual(m["pine_levels"], 2)
                self.assertEqual(m["paired_before_profile_gate"], 2)
                self.assertEqual(len(audit["rows"]), 4)
                original = profile(doc, ticker, DAY, ref, 10.)
                actual = {x["strike"]: x["net"] for x in original["rows"]}
                reported = {x["strike"]: x["net_gamma"] for x in audit["rows"]
                            if x["status"] == "COPPIA_VALIDA"}
                self.assertEqual(actual, reported)
                self.assertEqual(audit["rows"][0]["future_level"],
                                 ref * factor + 23.)
                self.assertIsNone(audit["rows"][2]["net_gamma"])

    def test_reject_wrong_future_mapping(self):
        doc, ref = self.fixture("DJX")
        with self.assertRaisesRegex(ValueError, "Conversione"):
            audit_strikes(doc, "DJX", DAY, ref, band=10.,
                          factor=1., basis=0.)

    def test_unusable_profile_still_reports_excluded_strikes(self):
        doc, ref = self.fixture("DJX")
        for item in doc["data"]["options"]:
            if item.get("option", "").endswith("P00520000"):
                item["gamma"] = None
        result = audit_strikes(doc, "DJX", DAY, ref, 10.,
                               factor=100., basis=None)
        self.assertFalse(result["metrics"]["profile_usable"])
        self.assertEqual(result["metrics"]["pine_levels"], 0)
        self.assertGreater(result["metrics"]["strikes_in_band"], 0)


if __name__ == "__main__":
    unittest.main()
