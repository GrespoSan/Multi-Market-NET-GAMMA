"""Native ETF NET GAMMA stays visible during Massive/API ratio outages.

Use deterministic fake Cboe rows and no external API. Chart tests verify
the Y axis is explicitly GLD/USO without a ratio and GC/CL only WITH an
internally consistent locked price pair. X gamma values remain unchanged.
"""
import unittest
from pathlib import Path

from etf_gamma_axes import chart_price_axes
from gamma_chart_style import spx_shared_gamma_bounds
from gld_cboe_view import _plot as plot_gld
from uso_cboe_view import _plot as plot_uso

ROOT = Path(__file__).resolve().parent.parent


def options_rows(base):
    result = []
    for strike, net in ((base-1.,-5.2),(base,12.7),(base+1.,3.1)):
        result.append({
            "strike": strike, "net": net, "call": abs(net) * 2.,
            "put": abs(net), "call_gamma": 0.01, "put_gamma": 0.02,
            "call_oi": 250., "put_oi": 200.,
            "call_volume": 25., "put_volume": 14.
        })
    return {"rows": result}


class ETFChartFallbackTests(unittest.TestCase):
    def test_both_etfs_draw_valid_gamma_in_original_etf_price_scale(self):
        for symbol, base, builder in (
            ("GLD", 359.0, plot_gld),
            ("USO", 158.0, plot_uso),
        ):
            with self.subTest(symbol=symbol):
                main = options_rows(base)
                weekly = options_rows(base)
                weekly["rows"] = [{**r,"net":r["net"]*.1} for r in weekly["rows"]]
                original_first = [x["net"] for x in main["rows"]]
                original_second = [x["net"] for x in weekly["rows"]]
                x = spx_shared_gamma_bounds([main, weekly])
                y = [base-3., base+3.]
                ticks = [base-1.,base,base+1.]
                axes = chart_price_axes(symbol, None, y, ticks)
                self.assertFalse(axes["projected"])
                self.assertEqual(axes["price_ratio"], 1.)
                self.assertEqual(axes["axis_symbol"], symbol)
                self.assertEqual(axes["y_range"], y)
                self.assertEqual(axes["tick_levels"], ticks)
                for label, group, original in (
                    ("0DTE",main,original_first),
                    ("Weekly",weekly,original_second),
                ):
                    fig = builder(
                        group, base, x, axes["y_range"],
                        price_ratio=axes["price_ratio"], projected=False,
                        title=label, tick_levels=axes["tick_levels"],
                    )
                    self.assertEqual(fig.layout.yaxis.title.text, f"Strike {symbol}")
                    self.assertEqual(list(fig.data[0].y),ticks)
                    self.assertEqual(list(fig.data[0].x),original)
                    self.assertEqual(list(fig.layout.yaxis.range),y)
                    self.assertEqual(list(fig.layout.xaxis.range),list(x))
                    self.assertNotIn("proiettato",fig.layout.yaxis.title.text)
                    self.assertTrue(any(a.text == f"Close prec. {symbol}"
                                        for a in fig.layout.annotations))

    def test_future_projection_requires_consistent_market_specific_ratio(self):
        for symbol, future, base, ratio, builder in (
            ("GLD", "GC",359., 11.1, plot_gld),
            ("USO", "CL",158., .62,plot_uso),
        ):
            with self.subTest(symbol=symbol):
                etf_price = base
                pair = {"etf_symbol": symbol,"ratio":ratio,
                        "etf_price":etf_price,
                        "future_price":etf_price*ratio,
                        "future_tv_symbol":f"EXCHANGE:{future}Z2026",
                        "bar_ny":"2026-11-04T10:30:00-05:00"}
                y=[base-3.,base+3.]
                ticks=[base-1.,base,base+1.]
                axes=chart_price_axes(symbol,pair,y,ticks)
                self.assertTrue(axes["projected"])
                group=options_rows(base)
                fig=builder(group,base,[-20,20],axes["y_range"],
                            price_ratio=axes["price_ratio"],projected=True,
                            title="0DTE",tick_levels=axes["tick_levels"])
                self.assertEqual(fig.layout.yaxis.title.text,f"Strike {future}")
                self.assertEqual(list(fig.data[0].x),[-5.2,12.7,3.1])
                self.assertAlmostEqual(float(fig.data[0].y[0]),(base-1.)*ratio)
                self.assertTrue(any(a.text=="Close prec. proiettato"
                                    for a in fig.layout.annotations))
                bad=dict(pair,etf_symbol="USO" if symbol=="GLD" else "GLD")
                self.assertFalse(chart_price_axes(symbol,bad,y,ticks)["projected"])
                bad=dict(pair,ratio=ratio*2)
                self.assertFalse(chart_price_axes(symbol,bad,y,ticks)["projected"])
                bad=dict(pair,future_tv_symbol="EXCHANGE:INVALID")
                self.assertFalse(chart_price_axes(symbol,bad,y,ticks)["projected"])
                self.assertFalse(chart_price_axes(symbol,{"ratio":float("nan")},y,ticks)["projected"])

    def test_ratio_failure_cannot_hide_the_chart_in_either_view(self):
        for file,symbol in (
            ("gld_cboe_view.py","GLD"),
            ("uso_cboe_view.py","USO")
        ):
            text=(ROOT / file).read_text(encoding="utf-8")
            with self.subTest(symbol=symbol):
                self.assertIn(f'axes = chart_price_axes("{symbol}", mapping, ylim, shared_ticks)',text)
                self.assertIn('fig = _plot(shown, reference, gamma_x, axes["y_range"]',text)
                self.assertIn('st.plotly_chart(fig, use_container_width=True,',text)
                self.assertNotIn("if mapping is not None and ratio is not None:",text)
                self.assertIn("STRIKE ETF ORIGINALI",text)
                self.assertIn(f"Rapporto {symbol}→",text)
                self.assertIn(f'render_etf_pine_exports("{symbol}"',text)


if __name__ == "__main__":
    unittest.main()
