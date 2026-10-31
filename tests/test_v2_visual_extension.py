"""Cross-market visual Gamma extension, no network and no synthetic strikes."""
import unittest
from copy import deepcopy

from v2_visual_extension import expanded_display


def mk(band):
    all_rows = [{"strike": float(n),
                 "net": float(n - 100) * 0.13,
                 "call": 3.0, "put": 1.0}
                for n in range(82, 119, 1)]
    rows = [r for r in all_rows if
            100 * (1-band/100) <= r["strike"] <= 100*(1+band/100)]
    return {"expiry": "2026-10-30", "usable": True, "rows": rows,
            "complete_strikes": len(rows)}


class TestV2VisualExtension(unittest.TestCase):
    def test_visual_adds_real_rows_and_preserves_original(self):
        original = mk(3)
        saved = deepcopy(original)
        shown, info = expanded_display(
            original, mk, 100.0, 94.0, 3.0,
            strike_field="strike", gamma_field="net")
        self.assertGreater(info["extra"], 0)
        self.assertEqual(original, saved)
        self.assertEqual(len(shown["rows"]), len(original["rows"])+info["extra"])
        known = {r["strike"] for r in mk(10)["rows"]}
        self.assertTrue(all(r["strike"] in known for r in shown["rows"]))
        core = {r["strike"]: r["net"] for r in original["rows"]}
        shown_map = {r["strike"]: r["net"] for r in shown["rows"]}
        self.assertTrue(all(shown_map[k] == v for k,v in core.items()))

    def test_when_original_wide_enough_it_is_identical(self):
        original=mk(10)
        shown, info = expanded_display(
            original, mk, 100.0, 99.5, 10.0,
            strike_field="strike", gamma_field="net")
        self.assertIs(shown, original)
        self.assertEqual(info["extra"], 0)

    def test_140_is_hard_extra_limit_but_original_is_never_truncated(self):
        original = {"expiry": "2026-10-30",
                    "rows": [{"strike": float(x), "net": float(x)}
                             for x in range(155)]}
        shown, info = expanded_display(
            original, mk, 100.0, 80.0, 3.0,
            strike_field="strike", gamma_field="net")
        self.assertIs(shown, original)
        self.assertEqual(len(shown["rows"]), 155)
        self.assertEqual(info["extra"], 0)

    def test_wider_gamma_mismatch_fails_closed(self):
        original = mk(3)
        def tampered(b):
            r = mk(b)
            if b > 3:
                for row in r["rows"]:
                    if row["strike"] == 100:
                        row["net"] = -500
            return r
        shown, info = expanded_display(
            original, tampered, 100.0, 95.0, 3.0,
            strike_field="strike", gamma_field="net")
        self.assertIs(shown, original)
        self.assertFalse(info["complete"])


if __name__ == "__main__":
    unittest.main()
