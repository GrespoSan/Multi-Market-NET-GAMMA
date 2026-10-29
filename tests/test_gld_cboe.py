"""Regression checks for manual Cboe GLD, not CME GC options."""
import gzip
import json
import unittest
from datetime import date

from gld_cboe import (GLD_URL, download_gld, read_gld, parse_contract, expirations,
                      next_weekly, close_previous, profile)


def sample(symbol="GLD"):
    items = []
    for day in (date(2026, 10, 29), date(2026, 10, 30)):
        for strike in (365, 366, 367):
            for side, oi, volume, gamma in (("C", 12, 3, .11), ("P", 8, 2, .15)):
                items.append({"option": f"GLD{day:%y%m%d}{side}{strike * 1000:08d}",
                              "open_interest": oi, "volume": volume, "gamma": gamma})
    return {"symbol": symbol, "timestamp": "2026-10-29 13:20:00",
            "data": {"prev_day_close": 366.1, "current_price": 366.8, "options": items}}


class TestCboeGold(unittest.TestCase):
    def test_read_original_json_and_gzip(self):
        blob = json.dumps(sample()).encode()
        self.assertEqual(read_gld(blob)["symbol"], "GLD")
        self.assertEqual(read_gld(gzip.compress(blob))["symbol"], "GLD")
        self.assertEqual(close_previous(read_gld(blob)), 366.1)
        self.assertEqual(expirations(read_gld(blob)), [date(2026, 10, 29), date(2026, 10, 30)])

    def test_reject_other_symbols(self):
        for symbol in ("SPX", "_NDX", "GC", ""):
            with self.assertRaisesRegex(ValueError, "Atteso GLD"):
                read_gld(json.dumps(sample(symbol)).encode())

    def test_contract_parser_and_friday(self):
        self.assertEqual(parse_contract("GLD261029P00365000"),
                         (date(2026, 10, 29), "put", 365.0))
        self.assertIsNone(parse_contract("SPX261029P00365000"))
        self.assertEqual(next_weekly(date(2026, 10, 29),
                                     [date(2026, 10, 30)]), date(2026, 10, 30))
        self.assertIsNone(next_weekly(date(2026, 10, 30),
                                      [date(2026, 10, 30)]))

    def test_unmodified_source_gamma_and_common_band(self):
        doc = sample()
        a = profile(doc, date(2026, 10, 29), 366.1, 3.0)
        b = profile(doc, date(2026, 10, 30), 366.1, 3.0)
        self.assertTrue(a["usable"])
        self.assertTrue(b["usable"])
        self.assertEqual(a["eligible"], 6)
        self.assertEqual(a["valid_contracts"], 6)
        self.assertEqual(a["complete_strikes"], 3)
        self.assertEqual(a["positive_gammas"], 6)
        self.assertAlmostEqual(a["rows"][0]["call"], (12 + 3) * .11)
        self.assertAlmostEqual(a["rows"][0]["put"], (8 + 2) * .15)
        self.assertAlmostEqual(a["rows"][0]["net"], 0.15)
        self.assertEqual(a["rows"], b["rows"])

    def test_missing_gamma_is_excluded_not_zero(self):
        doc = sample()
        for o in doc["data"]["options"]:
            if "261029" in o["option"]:
                o["gamma"] = None
        a = profile(doc, date(2026, 10, 29), 366.1)
        self.assertFalse(a["usable"])
        self.assertEqual(a["rows"], [])
        self.assertEqual(a["missing"]["Gamma"], 6)

    def test_zero_gamma_is_not_fake_positive(self):
        doc = sample()
        for o in doc["data"]["options"]:
            if "261029" in o["option"]:
                o["gamma"] = 0
        a = profile(doc, date(2026, 10, 29), 366.1)
        self.assertFalse(a["usable"])
        self.assertEqual(a["positive_gammas"], 0)

    def test_duplicate_contracts_fail(self):
        doc = sample()
        doc["data"]["options"].append(dict(doc["data"]["options"][0]))
        with self.assertRaisesRegex(ValueError, "duplicato"):
            profile(doc, date(2026, 10, 29), 366.1)

    def test_reject_missing_oi(self):
        doc = sample()
        for o in doc["data"]["options"]:
            if "261029" in o["option"] and o["option"][9:10] == "C":
                o["open_interest"] = None
        a = profile(doc, date(2026, 10, 29), 366.1)
        self.assertFalse(a["usable"])
        self.assertEqual(a["rows"], [])


    def test_download_gld_uses_original_url_and_is_validated(self):
        payload = json.dumps(sample()).encode("utf-8")
        class FakeResponse:
            status_code = 200
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def raise_for_status(self): pass
            def iter_content(self, chunk_size): yield payload

        class FakeSession:
            def get(self, url, **kwargs):
                self.url, self.kwargs = url, kwargs
                return FakeResponse()

        session = FakeSession()
        raw = download_gld(session=session)
        self.assertEqual(raw, payload)
        self.assertEqual(session.url, GLD_URL)
        self.assertTrue(session.kwargs["stream"])
        self.assertEqual(read_gld(raw)["symbol"], "GLD")

    def test_download_gld_rejects_non_gld_without_replacing_cached(self):
        payload = json.dumps(sample("SPX")).encode()
        class FakeResponse:
            status_code = 200
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def raise_for_status(self): pass
            def iter_content(self, chunk_size): yield payload
        class FakeSession:
            def get(self, url, **kwargs): return FakeResponse()
        with self.assertRaisesRegex(ValueError, "Atteso GLD"):
            download_gld(session=FakeSession())

    def test_download_gld_denies_blocked_response(self):
        class FakeResponse:
            status_code = 403
            def __enter__(self): return self
            def __exit__(self, *args): return False
        class FakeSession:
            def get(self, url, **kwargs): return FakeResponse()
        with self.assertRaisesRegex(RuntimeError, "HTTP 403"):
            download_gld(session=FakeSession())



if __name__ == "__main__":
    unittest.main()
