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


    def test_uso_histogram_uses_cl_strikes_and_preserves_original_gamma(self):
        rows = etf_rows()
        ratio = 0.6110189573459716
        lo, hi = 160 * ratio, 171 * ratio
        fig = profile_chart(
            rows, "USO", 165, [-200, 200], [lo, hi],
            price_scale=ratio, axis_symbol="CL",
            close_label="Close prec. proiettato",
            title="Principale", tick_levels=[r["strike"] * ratio for r in rows])
        self.assertEqual(fig.layout.yaxis.title.text, "Strike CL")
        self.assertEqual(list(fig.data[0].x), [r["net"] for r in rows])
        self.assertAlmostEqual(float(fig.data[0].y[0]), 160 * ratio)
        self.assertAlmostEqual(float(fig.data[0].y[-1]), 170 * ratio)
        self.assertAlmostEqual(float(fig.layout.yaxis.range[0]), lo)
        self.assertAlmostEqual(float(fig.layout.yaxis.range[1]), hi)
        self.assertEqual(list(fig.layout.xaxis.range), [-200, 200])
        self.assertEqual(list(fig.layout.yaxis.tickvals),
                         [r["strike"] * ratio for r in rows])
        self.assertIn("Livello CL: %{y:,.2f}",fig.data[0].hovertemplate)
        self.assertIn("Strike USO originale:",fig.data[0].hovertemplate)
        self.assertTrue(any(a.text=="Close prec. proiettato"
                            for a in fig.layout.annotations))
        self.assertTrue(any(abs(float(shape.y0)-165*ratio)<1e-7
                            for shape in fig.layout.shapes
                            if shape.y0 is not None and shape.y1==shape.y0))

    def test_gld_0dte_weekly_share_gc_axis_and_gamma_is_unchanged(self):
        ratio = 10.940670582614317
        original = etf_rows()
        weekly = [{**r, "net": r["net"] * .1} for r in original]
        xlim=spx_shared_gamma_bounds([{"rows":original},{"rows":weekly}])
        ticks=[r["strike"]*ratio for r in original]
        first=profile_chart(original,"GLD",165,xlim,[160*ratio,171*ratio],
                            price_scale=ratio,axis_symbol="GC",tick_levels=ticks)
        second=profile_chart(weekly,"GLD",165,xlim,[160*ratio,171*ratio],
                             price_scale=ratio,axis_symbol="GC",tick_levels=ticks)
        self.assertEqual(first.layout.yaxis.title.text,"Strike GC")
        self.assertEqual(list(first.layout.yaxis.range),list(second.layout.yaxis.range))
        self.assertEqual(list(first.layout.xaxis.range),list(second.layout.xaxis.range))
        self.assertEqual(list(first.data[0].x),[r["net"] for r in original])
        self.assertEqual(list(second.data[0].x),[r["net"] for r in weekly])
        self.assertEqual(list(first.data[0].y),[r["strike"]*ratio for r in original])
        self.assertEqual(list(second.data[0].y),[r["strike"]*ratio for r in weekly])

    def test_nasdaq_translates_ndx_to_nq_without_changing_gamma(self):
        original=[{"strike_index": 27450., "net_gamma": -20.,
                   "call_gamma": 2., "put_gamma": 22.},
                  {"strike_index": 27500., "net_gamma": 15.,
                   "call_gamma": 17., "put_gamma": 2.}]
        fig=profile_chart(original,"NDX",27450,[-30,25],[27550,27800],
                          level_field="strike_index",gamma_field="net_gamma",
                          ndx=True,price_shift=140.,axis_symbol="NQ",
                          close_label="Close prec. proiettato")
        self.assertEqual(fig.layout.yaxis.title.text,"Strike NQ")
        self.assertEqual(list(fig.data[0].y),[27590.,27640.])
        self.assertEqual(list(fig.data[0].x),[-20.,15.])
        self.assertIn("Livello NQ: %{y:,.2f}",fig.data[0].hovertemplate)

    def test_bad_future_ratio_must_be_rejected(self):
        rows=etf_rows()
        for invalid in (0.,-1.,float("nan"),float("inf")):
            with self.subTest(ratio=invalid):
                with self.assertRaises(ValueError):
                    profile_chart(rows,"USO",165,[-200,200],[0,200],
                                  price_scale=invalid,axis_symbol="CL")

    def test_market_pages_share_mapping_with_pine_and_never_modify_gamma_csv(self):
        from pathlib import Path
        root=Path(__file__).resolve().parent.parent
        for source,symbol,future in (
            ("gld_cboe_view.py","GLD","GC"),
            ("uso_cboe_view.py","USO","CL")):
            with self.subTest(symbol=symbol):
                page=(root/source).read_text(encoding="utf-8")
                self.assertIn(f'load_chart_continuous_mapping(',page)
                self.assertNotIn("prepare_locked_chart_mapping(",page)
                self.assertIn(f'chart_price_axes("{symbol}", mapping, ylim, shared_ticks)',page)
                self.assertIn('price_ratio=axes["price_ratio"], projected=True',page)
                self.assertIn('st.plotly_chart(fig, use_container_width=True,',page)
                self.assertIn("render_etf_pine_exports(",page)
                self.assertIn('_to_csv(p["rows"])',page)
                self.assertIn(f'axis_symbol="{future}" if projected else None',page)

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
