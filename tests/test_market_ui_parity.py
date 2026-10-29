"""One identical top-screen UI for Nasdaq NDX, Gold GLD and Petrolio USO."""
import ast
from pathlib import Path
import unittest

from market_ui import MARKET_DISPLAY, PAGE_STYLE, UPLOAD_KEYS

ROOT = Path(__file__).resolve().parent.parent


def source(path):
    return (ROOT / path).read_text(encoding="utf-8")


def calls_by_name(module, func):
    tree = ast.parse(source(module))
    return [node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == func]


class CommonMarketLayoutTests(unittest.TestCase):
    def test_all_market_headers_have_one_shared_structure(self):
        self.assertEqual(list(MARKET_DISPLAY), ["NASDAQ", "GOLD", "WTI"])
        self.assertEqual(UPLOAD_KEYS, {
            "NDX": "ndx_upload",
            "GLD": "gld_cboe_upload",
            "USO": "uso_cboe_upload"})
        # A fixed desktop cap compressed the 0DTE and Weekly side-by-side plots.
        self.assertIn("max-width: none !important", PAGE_STYLE)
        self.assertIn("width: 100% !important", PAGE_STYLE)
        self.assertIn('data-testid="stMainBlockContainer"', PAGE_STYLE)
        self.assertNotIn("max-width: 1460px", PAGE_STYLE)
        for filename in ("app.py", "gld_cboe_view.py", "uso_cboe_view.py"):
            with self.subTest(page=filename):
                src = source(filename)
                self.assertTrue(
                    "gap='medium'" in src or 'gap="medium"' in src,
                    "I grafici paralleli devono mantenere spaziatura compatta."
                )
        style = source("gamma_chart_style.py")
        self.assertIn("height=plot_height", style)
        self.assertIn("plot_height = max(520, 760)", style)
        self.assertIn("autosize=True", style)
        self.assertIn("bar_height = min(", style)
        self.assertIn("range=common_x", style)
        self.assertIn("range=shared_y", style)
        self.assertIn("@media (max-width: 800px)", PAGE_STYLE)
        app = source("app.py")
        self.assertEqual(len(calls_by_name("app.py", "render_dashboard_header")), 1)
        self.assertNotIn("st.title('Multi-Market", app)

    def test_acquisition_controls_are_shared_by_all_markets(self):
        for filename, symbol in (("app.py", "NDX"),
                                 ("gld_cboe_view.py", "GLD"),
                                 ("uso_cboe_view.py", "USO")):
            with self.subTest(market=symbol):
                self.assertEqual(len(calls_by_name(filename,
                                                   "render_acquisition_controls")), 1)
                self.assertEqual(len(calls_by_name(filename,
                                                   "render_empty_snapshot")), 1)
                self.assertEqual(len(calls_by_name(filename,
                                                   "archive_panel")), 1)
                # No independent layout/upload implementations can silently diverge.
                self.assertNotIn("st.file_uploader(", source(filename))
                self.assertNotIn("st.subheader(\"Fotografia Cboe", source(filename))
                self.assertIn(f'archive_panel("{symbol}")'
                              if symbol != "NDX" else "archive_panel('NDX')",
                              source(filename))

    def test_same_import_and_archive_controls_in_same_order(self):
        ui = source("market_ui.py")
        self.assertIn("Importazione manuale JSON originale", ui)
        self.assertIn('st.subheader(f"Fotografia opzioni Cboe · {symbol}")', ui)
        self.assertIn("uploaded = st.file_uploader(", ui)
        self.assertIn('key=f"{symbol.lower()}_cboe_fetch"', ui)
        for filename in ("gld_cboe_view.py", "uso_cboe_view.py"):
            s = source(filename)
            self.assertLess(s.index("render_acquisition_controls"),
                            s.index("archive_panel(\""))
        app = source("app.py")
        self.assertLess(app.index("fetch_pressed,uploaded=render_acquisition_controls"),
                        app.index("archive_selected=archive_panel"))

    def test_pine_and_gamma_calculations_stay_independent_of_layout(self):
        ui = source("market_ui.py")
        for term in ("make_pine(", "make_etf_future_pine(", "profile(",
                     "gammaPerCandle", "ratioToDraw"):
            self.assertNotIn(term, ui)


if __name__ == "__main__":
    unittest.main()
