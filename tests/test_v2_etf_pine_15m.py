"""ETF future Pine guards: Gold and Oil on 15m+ charts.

Both direct and timed-comparison exporters reuse the same future Pine template.
Gamma arrays and pricing methodology are not redefined in this fix.
"""
import unittest
from datetime import date
from etf_future_pine import make_etf_future_pine
from v2_pine_comparison import make_pine_comparison_v2


def profiles(symbol):
    base = 350.0 if symbol == "GLD" else 110.0
    def rows(x):
        return [{"strike": x, "net": 3.0}, {"strike": x+1, "net": -2.0}]
    return {"0DTE": {"usable": True, "expiry": "2026-11-12", "rows": rows(base)},
            "Weekly": {"usable": True, "expiry": "2026-11-13", "rows": rows(base+1)}}


class ETF15mRatioTests(unittest.TestCase):
    def check_code(self, code):
        self.assertIn('request.security_lower_tf(etfTicker, "5", [close[1], time[1]]', code)
        self.assertIn('request.security_lower_tf(contractTicker, "5", [close[1], time[1]]', code)
        self.assertIn("if timeframe.in_seconds() <= 300", code)
        self.assertIn("while i >= 0 and j >= 0", code)
        self.assertIn("et > lastMatchedTime", code)
        self.assertIn("lastDynamicRatio := fp / ep", code)
        self.assertIn('if barstate.islast and validTicker and not na(ratioToDraw)', code)
        self.assertIn("var array<float> mainGammaETF", code)

    def test_gold_continuous_15m_ratio(self):
        code = make_etf_future_pine("GLD", profiles("GLD"), 350.0,
                                    date(2026, 11, 12), "07:30",
                                    None, continuous=True)
        self.check_code(code)
        self.assertIn('"AMEX:GLD"', code)
        self.assertIn('COMEX:GC1!', code)

    def test_oil_continuous_15m_ratio(self):
        code = make_etf_future_pine("USO", profiles("USO"), 110.0,
                                    date(2026, 11, 12), "07:30",
                                    None, continuous=True)
        self.check_code(code)
        self.assertIn('"AMEX:USO"', code)
        self.assertIn('NYMEX:CL1!', code)


if __name__ == "__main__":
    unittest.main()
