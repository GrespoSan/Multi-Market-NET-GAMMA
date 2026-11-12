"""RUT/DJX Weekly regression: the user sees a valid Weekly by default.

Synthetic CBOE contract chains; never assert live CBOE coverage without
inspecting a dated and authenticated real snapshot.
"""
import unittest
from datetime import date
from pathlib import Path
from v2_index_weekly import weekly_candidates, choose_weekly
from v2_universal_cboe import expiries, profile

DAY = date(2026, 11, 12)
WEEK1 = date(2026, 11, 13)
WEEK2 = date(2026, 11, 20)


def contract(root, expiry, side, strike, gamma=0.15):
    return {"option": f"{root}{expiry:%y%m%d}{side}{int(round(strike * 1000)):08d}",
            "gamma": gamma, "open_interest": 50, "volume": 12}


def fixture(root, *, first_usable=True):
    mid = 520. if root == "DJX" else 2800.
    items = []
    for day, expiry_root in ((DAY, root), (WEEK1, root + "W"),
                             (WEEK2, root + "W")):
        for strike in (mid, mid + 1):
            items.append(contract(expiry_root, day, "C", strike))
            if day != WEEK1 or first_usable:
                items.append(contract(expiry_root, day, "P", strike))
    return {"symbol": "_" + root,
            "data": {"options": items, "prev_day_close": mid}}, mid


class WeeklyTests(unittest.TestCase):
    def test_friday_candidates_are_actual_dates_only(self):
        self.assertEqual(
            weekly_candidates([DAY, WEEK2, WEEK1, WEEK1], DAY),
            [WEEK1, WEEK2])
        self.assertEqual(weekly_candidates([DAY], DAY), [])

    def test_first_valid_weekly_selected_for_both_indices(self):
        for root in ("RUT", "DJX"):
            with self.subTest(root=root):
                doc, reference = fixture(root)
                real = expiries(doc, root)
                selected, group, diag = choose_weekly(
                    doc, root, DAY, reference, 10., real)
                self.assertEqual(selected, WEEK1)
                self.assertTrue(group["usable"])
                self.assertGreaterEqual(len(group["rows"]), 2)
                self.assertEqual([r["strike"] for r in group["rows"]],
                                 [reference, reference+1])
                self.assertEqual(group["rows"][0]["net"],
                                 profile(doc, root, WEEK1, reference, 10.)["rows"][0]["net"])

    def test_invalid_first_friday_skipped_without_forging_gamma(self):
        for root in ("RUT", "DJX"):
            with self.subTest(root=root):
                doc, ref = fixture(root, first_usable=False)
                selected, group, diag = choose_weekly(
                    doc, root, DAY, ref, 10., expiries(doc, root))
                self.assertEqual(selected, WEEK2)
                self.assertFalse(diag[WEEK1]["usable"])
                self.assertTrue(group["usable"])

    def test_no_weekly_reports_missing_instead_of_default_none(self):
        doc, reference = fixture("RUT")
        doc["data"]["options"] = [
            item for item in doc["data"]["options"]
            if item["option"].startswith("RUT261112")]
        chosen, group, details = choose_weekly(
            doc, "RUT", DAY, reference, 10., expiries(doc, "RUT"))
        self.assertIsNone(chosen)
        self.assertIsNone(group)
        self.assertEqual(details, {})

    def test_ui_and_pines_use_same_weekly_selector(self):
        root = Path(__file__).resolve().parents[1]
        for name in ("v2_index_market_view.py", "v2_index_timed_exports.py",
                     "v2_unified_pine.py"):
            code = (root/name).read_text(encoding="utf-8")
            self.assertIn("choose_weekly(", code, name)
        view = (root/"v2_index_market_view.py").read_text(encoding="utf-8")
        self.assertIn("st.session_state[weekly_key] = preferred_weekly", view)
        self.assertIn('"Weekly", weekly', view)


if __name__ == "__main__":
    unittest.main()
