"""Unified five-market timed 0DTE comparisons: verified fixtures only."""
import unittest
from datetime import date
from unittest.mock import patch
from v2_unified_timed import build_unified_comparison_pine, _checked_comparison
from v2_unified_pine import MARKETS
from v2_pine_session import slots_for_day

DAY = date(2026, 11, 12)
HIST = date(2026, 11, 11)


def record(symbol, *, sign=1., expiry=DAY):
    level = "strike_index" if symbol == "NDX" else "strike"
    value = "net_gamma" if symbol == "NDX" else "net"
    price = 28000. if symbol == "NDX" else 100.
    rows = [{level: price, value: 3.*sign},
            {level: price+1, value: -1.*sign}]
    week = [{level: price+2, value: 2.},
            {level: price+3, value: -2.}]
    return {
        "main": rows, "weekly": week, "call": [], "put": [],
        "field_level": level, "field_gamma": value,
        "scale": .1, "main_label": "0DTE",
        "main_expiry": expiry, "weekly_expiry": date(2026, 11, 13),
        "captured": {"stamp": "12/11/2026 15:51 CET"},
        "basis": 23.0 if symbol == "NDX" else 0.0,
    }


class UnifiedTimedTests(unittest.TestCase):
    def test_1550_has_three_real_columns_all_markets(self):
        cur = {m: record(m) for m in MARKETS}
        old = {m: record(m, sign=-1) for m in MARKETS}
        code = build_unified_comparison_pine(DAY, cur, old, "1550")
        self.assertEqual(code.count('indicator("'), 1)
        self.assertIn('UNICO 15:50', code)
        self.assertIn('showPrevious = input.bool(false', code)
        self.assertIn('renderProfile(prevMapped, previousGamma', code)
        self.assertIn('renderProfile(drawMain, mainGamma', code)
        self.assertIn('renderProfile(drawWeek, weekGamma', code)
        self.assertIn('mainKind + " 07:30 · precedente', code)
        self.assertIn('mainKind + " 15:50 · corrente', code)
        self.assertEqual(code.count('if barstate.islast and validTicker'), 1)
        self.assertIn('etfTime == futTime', code)
        self.assertIn('request.security_lower_tf(', code)
        self.assertNotIn("SPERIMENTALE", code)
        for market in MARKETS:
            self.assertIn(f'var array<float> {market}PrevLevels', code)
            self.assertIn(f'var array<float> {market}PrevGamma', code)

    def test_1700_uses_1550_real_prior(self):
        cur = {"RUT": record("RUT")}
        old = {"RUT": record("RUT", sign=-1)}
        code = build_unified_comparison_pine(DAY, cur, old, "1700")
        self.assertIn("UNICO 17:00", code)
        self.assertIn('mainKind + " 15:50 · precedente', code)
        self.assertIn('mainKind + " 17:00 · corrente', code)
        self.assertIn("var array<float> GLDPrevLevels = array.new_float()", code)

    def test_historical_2030_is_not_relabelled(self):
        old = {"RUT": record("RUT", expiry=HIST)}
        cur = {"RUT": record("RUT", expiry=HIST)}
        code = build_unified_comparison_pine(HIST, cur, old, "2030")
        self.assertIn("UNICO 20:30", code)
        self.assertIn('mainKind + " 15:50 · precedente', code)
        self.assertIn('mainKind + " 20:30 · corrente', code)
        self.assertEqual(slots_for_day(HIST)[-1], "2030")

    def test_mismatched_expiries_rejected(self):
        prev = record("NDX", expiry=DAY)
        cur = record("NDX", expiry=date(2026,11,13))
        with self.assertRaisesRegex(ValueError, "scadenze principali"):
            _checked_comparison(prev, cur, "NDX")

    def test_real_non_0dte_uso_same_expiry_can_be_compared(self):
        prev = record("USO", expiry=date(2026, 11, 13))
        cur = record("USO", expiry=date(2026, 11, 13))
        for item in (prev, cur):
            item["main_label"] = "Principale (non 0DTE)"
        code = build_unified_comparison_pine(
            DAY, {"USO": cur}, {"USO": prev}, "1550")
        self.assertIn('=> "Principale (non 0DTE)"', code)
        self.assertIn('showTop3Odte and mainKind == "0DTE"', code)
        self.assertIn('mainKind + " 15:50 · corrente', code)

    def test_mismatched_principal_types_and_expiries_rejected(self):
        prev = record("USO")
        cur = record("USO", expiry=date(2026, 11, 13))
        cur["main_label"] = "Principale (non 0DTE)"
        with self.assertRaisesRegex(ValueError, "tipo di profilo differente"):
            _checked_comparison(prev, cur, "USO")
        prev["main_label"] = "Principale (non 0DTE)"
        with self.assertRaisesRegex(ValueError, "scadenze principali"):
            _checked_comparison(prev, cur, "USO")

    def test_missing_previous_keeps_real_current_and_weekly(self):
        code = build_unified_comparison_pine(
            DAY, {"NDX": record("NDX")}, {}, "1550",
            reports={"USO": "N/D · Fotografia corrente 15:50 non trovata"})
        self.assertIn("bool haveData = array.size(mainLevels) > 0", code)
        self.assertNotIn("bool haveData = array.size(previousLevels)", code)
        self.assertIn('showPrevious = input.bool(false', code)
        self.assertIn("var array<float> NDXPrevLevels = array.new_float()", code)
        self.assertIn("Fotografia corrente 15:50 non trovata", code)
        self.assertIn("float effectiveScale", code)
        self.assertIn("unifiedReadableScale", code)
        self.assertIn("if previousVisible", code)

    def test_real_strike_budget_fail_closed(self):
        cur = record("DJX")
        prev = record("DJX")
        prev["main"] *= 240
        with self.assertRaisesRegex(ValueError, "oltre il limite"):
            _checked_comparison(prev, cur, "DJX")

    def test_unpaired_market_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "precedenti senza mercato corrente"):
            build_unified_comparison_pine(DAY,
                {"NDX": record("NDX")}, {"RUT": record("RUT")}, "1550")


if __name__ == "__main__":
    unittest.main()
