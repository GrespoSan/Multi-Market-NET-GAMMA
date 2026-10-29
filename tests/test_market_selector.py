"""The public Multi-Market selector deliberately contains exactly three markets."""
import unittest

from markets import MARKETS


class MarketSelectorTests(unittest.TestCase):
    def test_three_supported_markets_only(self):
        self.assertEqual(list(MARKETS), ["NASDAQ", "GOLD", "WTI"])
        self.assertTrue(all(m.enabled for m in MARKETS.values()))
        self.assertNotIn("DAX", MARKETS)
        self.assertNotIn("EURUSD", MARKETS)
        self.assertNotIn("ZB", MARKETS)


if __name__ == "__main__":
    unittest.main()
