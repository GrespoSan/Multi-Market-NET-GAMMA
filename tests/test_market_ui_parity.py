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
        for filename in ("v2_market_engine.py", "gld_cboe_view.py", "uso_cboe_view.py"):
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
        self.assertIn("render_selected_market(market_key)", app)
        self.assertNotIn("st.title('Multi-Market", app)

    def test_only_one_manual_acquisition_panel_serves_all_markets(self):
        # SPX-style emergency is the only manual Cboe widget surface.
        emergency = source("v2_emergency_pine.py")
        acquisition = source("v2_emergency_acquisition.py")
        for symbol in ("NDX", "GLD", "USO"):
            self.assertIn(f'"{symbol}"', acquisition)
        self.assertIn('st.button("Scarica CBOE adesso"', emergency)
        self.assertIn('st.file_uploader(', emergency)
        self.assertIn('st.button("Usa file importato"', emergency)
        self.assertIn('type=["zip", "json", "gz"]', emergency)
        self.assertIn('download_current_snapshot(symbol)', emergency)
        self.assertIn('activate_for_analysis(symbol, active)', emergency)
        for filename, symbol in (("v2_market_engine.py", "NDX"),
                                 ("gld_cboe_view.py", "GLD"),
                                 ("uso_cboe_view.py", "USO")):
            with self.subTest(market=symbol):
                src = source(filename)
                self.assertEqual(len(calls_by_name(filename,
                                                   "render_acquisition_controls")), 0)
                self.assertEqual(len(calls_by_name(filename,
                                                   "render_empty_snapshot")), 1)
                self.assertEqual(len(calls_by_name(filename,
                                                   "archive_panel")), 1)
                self.assertNotIn("st.file_uploader(", src)
                self.assertIn(f'archive_panel("{symbol}")'
                              if symbol != "NDX" else "archive_panel('NDX')",
                              src)

    def test_manual_capture_overrides_archive_without_duplicate_controls(self):
        acquisition = source("v2_emergency_acquisition.py")
        self.assertIn("def activate_for_analysis(symbol, active):", acquisition)
        self.assertIn("prefer_manual_source(symbol)", acquisition)
        self.assertIn('state["ndx_blob"] = verified["content"]', acquisition)
        self.assertIn("save(verified[", acquisition)
        self.assertIn("def use_uploaded_snapshot(symbol, filename, raw):", acquisition)
        for filename in ("v2_market_engine.py", "gld_cboe_view.py", "uso_cboe_view.py"):
            s = source(filename)
            self.assertLess(s.index("snapshot_placement = st.container()"),
                            s.index("with snapshot_placement:"))
            self.assertNotIn("with st.expander(\"Acquisizione Cboe / importazione manuale", s)
        app = source("app.py")
        self.assertIn("render_v2_emergency_pine(market_key)", app)

    def test_pine_and_gamma_calculations_stay_independent_of_layout(self):
        ui = source("market_ui.py")
        for term in ("make_pine(", "make_etf_future_pine(", "profile(",
                     "gammaPerCandle", "ratioToDraw"):
            self.assertNotIn(term, ui)


if __name__ == "__main__":
    unittest.main()
