"""Primary-market NET / CALL / PUT metrics: original CBOE Gamma unchanged."""
import unittest
from pathlib import Path
from v2_gamma_summary import gamma_totals, format_gamma_it

ROOT = Path(__file__).resolve().parents[1]


class PrimaryGammaSummaryTests(unittest.TestCase):
    def test_italian_numbers_and_signs(self):
        self.assertEqual(format_gamma_it(6076.19, signed=True), "+6.076,19")
        self.assertEqual(format_gamma_it(-6076.19, signed=True), "-6.076,19")
        self.assertEqual(format_gamma_it(26539.40, signed=True), "+26.539,40")
        self.assertEqual("−" + format_gamma_it(20463.21), "−20.463,21")

    def test_aggregates_only_displayed_groups_and_does_not_mutate(self):
        groups = [
            {"rows": [{"net": 7., "call": 9., "put": 2.}]},
            {"rows": [{"net": -4., "call": 1., "put": 5.}]},
        ]
        totals = gamma_totals(groups, net_key="net", call_key="call", put_key="put")
        self.assertEqual(totals, {"net": 3., "call": 10., "put": 7.})
        self.assertEqual(groups[0]["rows"][0]["net"], 7.)
        self.assertEqual(groups[1]["rows"][0]["put"], 5.)

    def test_ndx_uses_original_weighted_contributions(self):
        groups = [{"rows": [{"net_gamma": -2.5, "call_gamma": 4.0,
                             "put_gamma": 6.5}]}]
        self.assertEqual(gamma_totals(groups, net_key="net_gamma",
                                      call_key="call_gamma",
                                      put_key="put_gamma")["net"], -2.5)

    def test_all_five_market_views_call_shared_summary(self):
        for name in ("v2_index_market_view.py", "v2_market_engine.py",
                     "gld_cboe_view.py", "uso_cboe_view.py"):
            source = (ROOT/name).read_text(encoding="utf-8")
            self.assertIn("render_gamma_summary(", source, name)
        index = (ROOT/"v2_index_market_view.py").read_text()
        self.assertIn('render_gamma_summary(groups.values()', index)
        ndx = (ROOT/"v2_market_engine.py").read_text()
        self.assertIn('render_gamma_summary(visual_profiles.values()', ndx)
        for name in ("gld_cboe_view.py", "uso_cboe_view.py"):
            self.assertIn('render_gamma_summary(good,', (ROOT/name).read_text())

    def test_summary_labels_and_coverage_note(self):
        source = (ROOT/"v2_gamma_summary.py").read_text()
        for label in ("NET GAMMA · Call − Put", "GAMMA CALL (+)",
                      "GAMMA PUT (−)", "soli profili mostrati"):
            self.assertIn(label, source)


if __name__ == "__main__":
    unittest.main()
