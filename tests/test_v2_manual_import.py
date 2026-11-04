"""One shared ZIP/JSON import for NDX, GLD and USO (no disk or network)."""
import gzip
import io
import json
import unittest
import zipfile

from v2_manual_import import normalize_manual_upload
from ndx_engine import unpack_snapshot
from gld_cboe import read_gld
from uso_cboe import read_uso


def packaged(files):
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for key, content in files.items():
            z.writestr(key, content)
    return raw.getvalue()


def payload(symbol):
    return json.dumps({
        "symbol": symbol, "timestamp": "2026-11-04 09:30:00",
        "data": {"prev_day_close": 100, "current_price": 101, "options": []},
    }).encode()


class ImportTests(unittest.TestCase):
    def test_one_cboe_json_or_gzip_in_zip_per_market(self):
        parsers = {"NDX": unpack_snapshot, "GLD": read_gld, "USO": read_uso}
        for symbol in parsers:
            with self.subTest(symbol=symbol):
                expected = payload(symbol)
                got, name = normalize_manual_upload(
                    "cboe.zip",
                    packaged({"notes.txt": b"info", f"fotos/{symbol}_CBOE_snapshot.json": expected}),
                    symbol)
                self.assertEqual(got, expected)
                self.assertEqual(name, f"{symbol}_CBOE_snapshot.json")
                self.assertEqual(parsers[symbol](got)["symbol"], symbol)
                gz = gzip.compress(expected)
                wrapped, nested = normalize_manual_upload(
                    "bundle.ZIP", packaged({f"{symbol}_CBOE.json.gz": gz}), symbol)
                self.assertEqual(wrapped, gz)
                self.assertEqual(nested, f"{symbol}_CBOE.json.gz")
                self.assertEqual(parsers[symbol](wrapped)["symbol"], symbol)
                plain, filename = normalize_manual_upload(
                    "source.json.gz", gz, symbol)
                self.assertEqual(plain, gz)
                self.assertEqual(filename, "source.json.gz")

    def test_multiple_or_wrong_market_fails_not_guess(self):
        with self.assertRaisesRegex(ValueError, "un'unica fotografia"):
            normalize_manual_upload("a.zip",
                packaged({"NDX_a.json": payload("NDX"),
                          "NDX_b.json": payload("NDX")}), "NDX")
        with self.assertRaisesRegex(ValueError, "trovate 0"):
            normalize_manual_upload("b.zip",
                packaged({"GLD.json": payload("GLD")}), "NDX")
        with self.assertRaisesRegex(ValueError, "Percorso ZIP"):
            normalize_manual_upload("c.zip",
                packaged({"../NDX.json": payload("NDX")}), "NDX")

    def test_invalid_zip_and_extensions_fail(self):
        with self.assertRaisesRegex(ValueError, "danneggiato"):
            normalize_manual_upload("invalid.zip", b"not a zip", "USO")
        with self.assertRaisesRegex(ValueError, "consentiti"):
            normalize_manual_upload("a.csv", b"x", "NDX")
        with self.assertRaisesRegex(ValueError, "non supportato"):
            normalize_manual_upload("a.json", b"{}", "SPX")


if __name__ == "__main__":
    unittest.main()
