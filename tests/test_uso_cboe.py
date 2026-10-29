"""Regression checks for manual Cboe USO, not CME CL options."""
import gzip
import json
import unittest
from datetime import date

from uso_cboe import (USO_URL, download_uso, read_uso, parse_contract, expirations,
                      next_weekly, close_previous, profile)


def sample(symbol="USO"):
    items = []
    for day in (date(2026, 10, 29), date(2026, 10, 30)):
        for strike in (165, 166, 167):
            for side, oi, volume, gamma in (("C", 12, 3, .11), ("P", 8, 2, .15)):
                items.append({"option": f"USO{day:%y%m%d}{side}{strike * 1000:08d}",
                              "open_interest": oi, "volume": volume, "gamma": gamma})
    return {"symbol": symbol, "timestamp": "2026-10-29 13:20:00",
            "data": {"prev_day_close": 166.1, "current_price": 166.8, "options": items}}


class TestCboeOil(unittest.TestCase):
    def test_read_original_json_and_gzip(self):
        blob = json.dumps(sample()).encode()
        self.assertEqual(read_uso(blob)["symbol"], "USO")
        self.assertEqual(read_uso(gzip.compress(blob))["symbol"], "USO")
        self.assertEqual(close_previous(read_uso(blob)), 166.1)
        self.assertEqual(expirations(read_uso(blob)), [date(2026, 10, 29), date(2026, 10, 30)])

    def test_reject_other_symbols(self):
        for symbol in ("SPX", "_NDX", "GLD", "CL", ""):
            with self.assertRaisesRegex(ValueError, "Atteso USO"):
                read_uso(json.dumps(sample(symbol)).encode())

    def test_contract_parser_and_friday(self):
        self.assertEqual(parse_contract("USO261029P00165000"),
                         (date(2026, 10, 29), "put", 165.0))
        self.assertIsNone(parse_contract("SPX261029P00165000"))
        self.assertEqual(next_weekly(date(2026, 10, 29),
                                     [date(2026, 10, 30)]), date(2026, 10, 30))
        self.assertIsNone(next_weekly(date(2026, 10, 30),
                                      [date(2026, 10, 30)]))

    def test_unmodified_source_gamma_and_common_band(self):
        doc = sample()
        a = profile(doc, date(2026, 10, 29), 166.1, 3.0)
        b = profile(doc, date(2026, 10, 30), 166.1, 3.0)
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
        a = profile(doc, date(2026, 10, 29), 166.1)
        self.assertFalse(a["usable"])
        self.assertEqual(a["rows"], [])
        self.assertEqual(a["missing"]["Gamma"], 6)

    def test_zero_gamma_is_not_fake_positive(self):
        doc = sample()
        for o in doc["data"]["options"]:
            if "261029" in o["option"]:
                o["gamma"] = 0
        a = profile(doc, date(2026, 10, 29), 166.1)
        self.assertFalse(a["usable"])
        self.assertEqual(a["positive_gammas"], 0)

    def test_duplicate_contracts_fail(self):
        doc = sample()
        doc["data"]["options"].append(dict(doc["data"]["options"][0]))
        with self.assertRaisesRegex(ValueError, "duplicato"):
            profile(doc, date(2026, 10, 29), 166.1)

    def test_reject_missing_oi(self):
        doc = sample()
        for o in doc["data"]["options"]:
            if "261029" in o["option"] and o["option"][9:10] == "C":
                o["open_interest"] = None
        a = profile(doc, date(2026, 10, 29), 166.1)
        self.assertFalse(a["usable"])
        self.assertEqual(a["rows"], [])


    def test_download_uso_uses_original_url_and_is_validated(self):
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
        raw = download_uso(session=session)
        self.assertEqual(raw, payload)
        self.assertEqual(session.url, USO_URL)
        self.assertTrue(session.kwargs["stream"])
        self.assertEqual(read_uso(raw)["symbol"], "USO")

    def test_download_uso_rejects_non_uso_without_replacing_cached(self):
        payload = json.dumps(sample("SPX")).encode()
        class FakeResponse:
            status_code = 200
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def raise_for_status(self): pass
            def iter_content(self, chunk_size): yield payload
        class FakeSession:
            def get(self, url, **kwargs): return FakeResponse()
        with self.assertRaisesRegex(ValueError, "Atteso USO"):
            download_uso(session=FakeSession())

    def test_download_uso_denies_blocked_response(self):
        class FakeResponse:
            status_code = 403
            def __enter__(self): return self
            def __exit__(self, *args): return False
        class FakeSession:
            def get(self, url, **kwargs): return FakeResponse()
        with self.assertRaisesRegex(RuntimeError, "HTTP 403"):
            download_uso(session=FakeSession())



if __name__ == "__main__":
    unittest.main()
