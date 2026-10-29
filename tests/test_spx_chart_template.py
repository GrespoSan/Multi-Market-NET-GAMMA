"""The Serafini SPX histogram is the visual baseline for all Multi-Market plots.

Visual tests use synthetic numbers only: no Cboe data/algorithm is altered.
"""
import unittest

from gamma_chart_style import (SPX_GREEN, SPX_RED, SPX_ZERO, SPX_CLOSE,
                               spx_shared_gamma_bounds, profile_chart,
                               panel_heading, capture_display)


def etf_rows():
    rows = []
    for j in range(11):
        rows.append({
            "strike": 160.0 + j, "net": (-1 if j < 4 else 1) * (j + 1) * 5.0,
            "call": 40., "put": 30.,
            "call_gamma": .1, "put_gamma": .2,
            "call_oi": 90, "put_oi": 80,
            "call_volume": 5, "put_volume": 6,
        })
    return rows


class ReferenceSPXHistogramTests(unittest.TestCase):
    def test_very_thin_bars_even_with_only_eleven_etf_strikes(self):
        rows = etf_rows()
        fig = profile_chart(rows, "USO", 165.0, [-200, 200], [160, 171],
                            title="Principale", snapshot_label="Manuale 21:56 Roma")
        # 7 vertical pixels on a tall SPX style plot, never 80% of 1 strike.
        self.assertLess(float(fig.data[0].width), 0.14)
        self.assertEqual(fig.layout.height, 760)
        self.assertEqual(fig.data[0].orientation, "h")
        self.assertEqual(fig.data[0].marker.color[0], SPX_RED)
        self.assertEqual(fig.data[0].marker.color[-1], SPX_GREEN)
        self.assertEqual(fig.layout.paper_bgcolor, "#0e1017")
        self.assertEqual(fig.layout.yaxis.title.text, "Strike USO")
        self.assertIn("NET GAMMA per strike", fig.layout.title.text)
        self.assertNotIn("Gamma positivo più marcato", fig.layout.title.text)
        self.assertEqual(list(fig.data[0].x), [r["net"] for r in rows])
        self.assertEqual(list(fig.data[0].y), [r["strike"] for r in rows])
        self.assertEqual(list(fig.layout.xaxis.range), [-200, 200])
        self.assertEqual(list(fig.layout.yaxis.range), [160, 171])
        self.assertEqual(fig.layout.xaxis.zerolinecolor, SPX_ZERO)
        self.assertGreaterEqual(len(fig.layout.shapes), 6)
        self.assertTrue(any(a.text == "Close prec." for a in fig.layout.annotations))
        self.assertTrue(any(a.text == "+1,0%" for a in fig.layout.annotations))

    def test_both_panels_identical_axis_bounds_unscaled_gamma(self):
        main = {"rows": etf_rows()}
        weekly = {"rows": [{**r, "net": r["net"] * .03} for r in etf_rows()]}
        shared = spx_shared_gamma_bounds([main, weekly])
        first = profile_chart(main["rows"], "GLD", 165.0, shared, [160, 171],
                              title="0DTE")
        second = profile_chart(weekly["rows"], "GLD", 165.0, shared, [160, 171],
                               title="Weekly")
        self.assertEqual(list(first.layout.xaxis.range), list(second.layout.xaxis.range))
        self.assertEqual(list(first.layout.yaxis.range), list(second.layout.yaxis.range))
        self.assertEqual(list(second.data[0].x), [r["net"] for r in weekly["rows"]])
        self.assertEqual(first.data[0].width, second.data[0].width)

    def test_source_timestamp_never_converted_to_italian_timezone(self):
        title, info = panel_heading(
            "0DTE", "2026-10-29", "2026-10-29 20:55:31",
            "2026-10-29T21:56:13+01:00", "Acquisizione diretta su richiesta")
        self.assertIn("RILEVAMENTO 29/10/2026", title)
        self.assertIn("download ore 21:56 Roma", title)
        self.assertIn("20:55:31 (fuso non dichiarato)", info)
        no_clock, label = capture_display("2026-10-29 20:55:31", "", "Importazione manuale")
        self.assertEqual(no_clock, "29/10/2026")
        self.assertIn("ora download non disponibile", label)

    def test_ndx_basis_affects_only_y_coordinate(self):
        raw = [{"strike_index": 7000, "net_gamma": -10.,
                "call_gamma": 4., "put_gamma": 14.},
               {"strike_index": 7005, "net_gamma": 5.,
                "call_gamma": 8., "put_gamma": 3.}]
        fig = profile_chart(raw,"NDX",7000,[-20, 10],[7010, 7025],
                            ndx=True,price_shift=15,
                            level_field="strike_index",gamma_field="net_gamma")
        self.assertEqual(list(fig.data[0].x), [-10., 5.])
        self.assertEqual(list(fig.data[0].y), [7015., 7020.])


if __name__ == "__main__":
    unittest.main()
