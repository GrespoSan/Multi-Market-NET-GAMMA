"""Visual-only formatting and labels of Universal CBOE Gamma totals."""
import unittest
from pathlib import Path
from v2_universal_cboe import format_gamma_it

class UniversalGammaFormattingTests(unittest.TestCase):
    def test_italian_signs_and_separators(self):
        self.assertEqual(format_gamma_it(6076.19, signed=True), "+6.076,19")
        self.assertEqual(format_gamma_it(-6076.19, signed=True), "-6.076,19")
        self.assertEqual(format_gamma_it(26539.40, signed=True), "+26.539,40")
        self.assertEqual("−" + format_gamma_it(20463.21), "−20.463,21")
    def test_no_original_calculation_change(self):
        code = (Path(__file__).resolve().parents[1]/"v2_universal_cboe.py").read_text()
        self.assertIn('net = sum(r["net"] for r in allrows)', code)
        self.assertIn('calls = sum(r["call"] for r in allrows)', code)
        self.assertIn('puts = sum(r["put"] for r in allrows)', code)
        for label in ("NET GAMMA · Call − Put", "GAMMA CALL (+)", "GAMMA PUT (−)"):
            self.assertIn(label, code)

if __name__ == "__main__":
    unittest.main()
