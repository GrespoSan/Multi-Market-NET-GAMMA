"""Guard the 4-argument page-to-Pine interface against Streamlit hot reload errors."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent


class PineViewIntegrationTests(unittest.TestCase):
    def test_market_pages_call_exporter_with_four_positional_args_only(self):
        for filename in ("gld_cboe_view.py", "uso_cboe_view.py"):
            with self.subTest(page=filename):
                tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
                calls = [node for node in ast.walk(tree)
                         if isinstance(node, ast.Call)
                         and isinstance(node.func, ast.Name)
                         and node.func.id == "render_etf_pine_exports"]
                self.assertEqual(len(calls), 1)
                self.assertEqual(len(calls[0].args), 4)
                self.assertEqual(calls[0].keywords, [])

    def test_pine_view_uses_same_session_keys_as_market_pages(self):
        from inspect import signature
        from etf_pine_view import render_etf_pine_exports
        params = signature(render_etf_pine_exports).parameters
        self.assertEqual(list(params)[:4], ["symbol", "calculated", "reference", "day"])
        self.assertIsNone(params["source_sha"].default)
        self.assertIsNone(params["cboe_stamp"].default)
        page = (ROOT / "etf_pine_view.py").read_text(encoding="utf-8")
        self.assertIn('prefix + "sha256"', page)
        self.assertIn('prefix + "timestamp"', page)
        for instrument in ("gld", "uso"):
            source = (ROOT / f"{instrument}_cboe_view.py").read_text(encoding="utf-8")
            self.assertIn(f'["{instrument}_cboe_timestamp"] = stamp', source)
            self.assertIn(f'["{instrument}_cboe_sha256"] = digest', source)


if __name__ == "__main__":
    unittest.main()
