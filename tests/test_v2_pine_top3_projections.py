"""0DTE top-3 projection parity: Multi-Market current, timed and Emergency Pine.

All synthetic data; no CBOE, Yahoo, Massive, TradingView or Supabase requests.
"""
import json
import re
import unittest
from datetime import date
from unittest.mock import patch

from pine_export import _top_gamma_rows, make_pine
from etf_future_pine import make_etf_future_pine
from v2_pine_session import parse_archived_capture
from v2_pine_timed_exports import produce_timed_scripts
from v2_emergency_pine import build_current_pine

DAY = date(2026, 11, 4)
WEEK = date(2026, 11, 6)
SIGNS = [2., -3., 8., -9., 5., -6., 0., 1., -2.]


def group(symbol, expiry=DAY, offset=0.0):
    base = {"NDX": 25500., "GLD": 368., "USO": 168.}[symbol] + offset
    field, gamma_field = (
        ("strike_index", "net_gamma") if symbol == "NDX" else ("strike", "net"))
    rows = [{field: base + i * (5. if symbol == "NDX" else 1.),
             gamma_field: value}
            for i, value in enumerate(SIGNS)]
    return {
        "expiry": expiry.isoformat(), "rows": rows,
        **({"band_pct": 3.} if symbol == "NDX" else {"usable": True}),
    }


def array_values(code, name):
    marker = "var array<float> " + name + " = "
    assert code.count(marker) == 1, name
    tail = code.split(marker, 1)[1]
    if tail.startswith("array.new_float()"):
        return []
    match = re.match(r"array.from\\((.*?)\\)", tail, re.DOTALL)
    assert match is not None, (name, tail[:100])
    return [float(x.strip()) for x in match.group(1).split(",")]


def assert_guides(test, code, left_name, right_name, *, count=6):
    test.assertIn('showTop3Odte = input.bool(true, "Proietta Top 3 Call / Put 0DTE")', code)
    test.assertIn("drawOdteTopProjections(array<float> callLevels", code)
    test.assertIn("line.new(bar_index, y, bar_index + 1, y", code)
    test.assertIn("extend=extend.right, color=positiveColor, style=line.style_dashed, width=1", code)
    test.assertIn("extend=extend.right, color=negativeColor, style=line.style_dashed, width=1", code)
    test.assertEqual(code.count("if showTop3Odte"), 1)
    test.assertEqual(code.count("drawOdteTopProjections("), 2)
    test.assertEqual(code.count("line.new(bar_index, y, bar_index + 1, y"), 2)
    helper = code.split("drawOdteTopProjections(array<float>", 1)[1].split(
        "if barstate.islast and validTicker", 1)[0]
    test.assertNotIn("label.new(", helper)
    test.assertNotIn("weeklyLevels", helper)
    test.assertIn("drawOdteTopProjections(" + left_name + ", " + right_name + ")", code)


class MultiMarketTop3(unittest.TestCase):
    def test_select_real_top3_each_side_and_skip_zeros(self):
        rows = group("NDX")["rows"]
        positive = _top_gamma_rows(rows, "strike_index", "net_gamma", positive=True)
        negative = _top_gamma_rows(rows, "strike_index", "net_gamma", positive=False)
        self.assertEqual([x["net_gamma"] for x in positive], [8., 5., 2.])
        self.assertEqual([x["net_gamma"] for x in negative], [-9., -6., -3.])
        self.assertEqual(len(_top_gamma_rows(rows[:1], "strike_index", "net_gamma",
                                             positive=False)), 0)
        self.assertEqual(_top_gamma_rows(
            [{"strike": 100., "net": 0.}], "strike", "net", positive=True), [])
        self.assertEqual(_top_gamma_rows(
            [{"strike": 100., "net": 0.}], "strike", "net", positive=False), [])

    def test_ndx_current_uses_basis_once_and_no_weekly_levels(self):
        code = make_pine(
            {"0DTE": group("NDX"), "Weekly": group("NDX", WEEK, 100.)},
            140., DAY, "CORRENTE")
        assert_guides(self, code, "topCallOdteLevels", "topPutOdteLevels")
        self.assertEqual(array_values(code, "topCallOdteLevels"),
                         [25650., 25660., 25640.])
        self.assertEqual(array_values(code, "topPutOdteLevels"),
                         [25655., 25665., 25645.])
        self.assertIn('syminfo.root == "NQ"', code)
        self.assertIn('syminfo.root == "MNQ"', code)

    def test_etf_continuous_uses_same_ratio_as_histogram(self):
        for sym, valid in (("GLD", "COMEX:GC1!"), ("USO", "NYMEX:CL1!")):
            with self.subTest(symbol=sym):
                code = make_etf_future_pine(
                    sym, {"0DTE": group(sym), "Weekly": group(sym, WEEK, 100.)},
                    370. if sym == "GLD" else 170.,
                    DAY, "CONTINUO", None, continuous=True)
                assert_guides(self, code, "topCallFutures", "topPutFutures")
                self.assertEqual(len(array_values(code, "topCallStrikesETF")), 3)
                self.assertEqual(len(array_values(code, "topPutStrikesETF")), 3)
                self.assertIn("array<float> odteLevels = mapETF(mainStrikesETF, ratioToDraw)", code)
                self.assertIn("array<float> topCallFutures = mapETF(topCallStrikesETF, ratioToDraw)", code)
                self.assertIn("array<float> topPutFutures = mapETF(topPutStrikesETF, ratioToDraw)", code)
                self.assertIn("and not na(ratioToDraw)", code)
                self.assertIn('ticker.standard(syminfo.tickerid) == "' + valid + '"', code)
                self.assertNotIn("float lockedRatio = 0.0", code)
                self.assertEqual(code.count("request.security("), 2)

    def test_non_0dte_primary_and_weekly_do_not_project(self):
        for sym in ("GLD", "USO"):
            with self.subTest(symbol=sym):
                code = make_etf_future_pine(
                    sym, {"Principale": group(sym), "Weekly": group(sym, WEEK)},
                    170., DAY, "PRINCIPALE", None, continuous=True)
                self.assertIn("var array<float> topCallStrikesETF = array.new_float()", code)
                self.assertIn("var array<float> topPutStrikesETF = array.new_float()", code)
                self.assertNotIn("if showTop3Odte", code)
                self.assertNotIn("drawOdteTopProjections(topCallFutures", code)

    def test_emergency_uses_same_top3_for_three_markets(self):
        for sym, ref, ratio in (("NDX", 25500., 125.),
                                ("GLD", 368., None),
                                ("USO", 168., None)):
            with self.subTest(symbol=sym):
                opts = []
                base = int(ref)
                step = 10 if sym == "NDX" else 1
                for exp in (DAY, WEEK):
                    for i, value in enumerate(SIGNS):
                        strike = base + step * i
                        call_oi, put_oi = ((60, 12) if value >= 0 else (12, 60))
                        for side, oi in (("C", call_oi), ("P", put_oi)):
                            opts.append({
                                "option": f"{sym}{exp:%y%m%d}{side}{strike * 1000:08d}",
                                "gamma": .01, "open_interest": oi, "volume": 5,
                            })
                raw = json.dumps({
                    "symbol": sym, "timestamp": "2026-11-04 13:30:00",
                    "data": {"prev_day_close": ref,
                             "current_price": ref + 2,
                             "options": opts},
                }).encode()
                pine = build_current_pine(sym, raw, DAY, ref, ratio,
                                          extension=False)["pine"]
                if sym == "NDX":
                    assert_guides(self, pine, "topCallOdteLevels", "topPutOdteLevels")
                else:
                    assert_guides(self, pine, "topCallFutures", "topPutFutures")
                    self.assertIn('modeRatio = "Dinamico"', pine)

    def test_timed_comparison_projects_current_not_previous_or_weekly(self):
        from v2_pine_timed_exports import SLOTS
        for sym in ("NDX", "GLD", "USO"):
            with self.subTest(symbol=sym):
                captures = {}
                frames = {}
                for i, (slot, utc) in enumerate(
                    (("0730", "063100"), ("1550", "145100"), ("2030", "195100"))
                ):
                    p = parse_archived_capture(
                        f"{sym}_20261104T{utc}Z_{slot}_{'a'*12}.json.gz", sym, DAY)
                    captures[slot] = p
                    frames[slot] = {
                        "0DTE": group(sym, offset=i * 1.),
                        "Weekly": group(sym, WEEK, offset=100.),
                        "capture": p, "close": {"NDX":25500., "GLD":368., "USO":168.}[sym],
                    }
                with patch("v2_pine_timed_exports.build_slot_profiles",
                           return_value=(frames, {})):
                    scripts, errors, _ = produce_timed_scripts(
                        sym, DAY, captures, frames["0730"]["close"],
                        3., 140. if sym == "NDX" else None)
                self.assertEqual(set(scripts), set(SLOTS), errors)
                for slot in SLOTS:
                    code = scripts[slot]
                    self.assertEqual(code.count("if showTop3Odte"), 1)
                    self.assertEqual(code.count("drawOdteTopProjections("), 2)
                    self.assertNotIn("line.new(bar_index - 1, y", code)
                    if slot != "0730":
                        self.assertIn("showPrevious = input.bool(true", code)
                        if sym == "NDX":
                            self.assertIn("drawOdteTopProjections(topCallOdteLevels, topPutOdteLevels)", code)
                        else:
                            self.assertIn("drawOdteTopProjections(topCallFutures, topPutFutures)", code)


if __name__ == "__main__":
    unittest.main()
