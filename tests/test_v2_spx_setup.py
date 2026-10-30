"""V2 architecture, no Supabase and authorized-only cron snapshots."""
import ast
import gzip
import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from cryptography.fernet import Fernet

from v2_cron import (run_capture, safe_url, validate_options,
                     fetch_authorized, CBOE_PUBLIC_URLS)
from v2_schedule import decision

ROOT = Path(__file__).resolve().parent.parent


def synthetic(symbol):
    root = symbol
    value = 30000 if symbol == "NDX" else (360 if symbol == "GLD" else 160)
    options = []
    for strike in (value, value + 1):
        for cp in ("C", "P"):
            options.append({
                "option": f"{root}261030{cp}{int(strike*1000):08d}",
                "gamma": .12, "open_interest": 40, "volume": 10
            })
    return json.dumps({
        "symbol": "_NDX" if symbol == "NDX" else symbol,
        "timestamp": "2026-10-29 15:45:00",
        "data": {"options": options, "prev_day_close": value}
    }).encode()


class V2SPXSetupTests(unittest.TestCase):
    def test_spx_shell_removed_modules_and_no_supabase(self):
        code = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('ANALISI DEL CONTESTO', code)
        self.assertIn('ANALISI NET GAMMA', code)
        self.assertIn("render_selected_market(market_key)", code)
        self.assertNotIn("from storage import Store", code)
        self.assertNotIn("from edge_triptych import", code)
        for forbidden in ("with st.expander('REPLAY E CONFRONTO'",
                          "with st.expander('REPORT GIORNALIERO AI'"):
            self.assertNotIn(forbidden, code)
        engine = (ROOT / "v2_market_engine.py").read_text(encoding="utf-8")
        self.assertIn("def render_selected_market(market_key):", engine)
        self.assertIn("from v2_storage_off import archive_panel", engine)
        for path in ("gld_cboe_view.py", "uso_cboe_view.py"):
            self.assertIn("from v2_storage_off import archive_panel",
                          (ROOT / path).read_text(encoding="utf-8"))
        remote = (ROOT / "v2_storage_off.py").read_text(encoding="utf-8")
        self.assertNotIn("from multimarket_archive import", remote)
        self.assertNotIn("requests.", remote)

    def test_chicago_dst_and_stable_rome_slot_names(self):
        # Before US daylight saving ends: Italy is only 6 hours ahead.
        cases = [
            (datetime(2026, 10, 30, 6, 30, tzinfo=timezone.utc),
             "30 7 * * 1-5", "07:30", "Europe/Rome", "07:30"),
            (datetime(2026, 10, 30, 13, 50, tzinfo=timezone.utc),
             "50 8 * * 1-5", "15:50", "America/Chicago", "14:50"),
            (datetime(2026, 10, 30, 18, 30, tzinfo=timezone.utc),
             "30 13 * * 1-5", "20:30", "America/Chicago", "19:30"),
            (datetime(2026, 11, 2, 14, 50, tzinfo=timezone.utc),
             "50 8 * * 1-5", "15:50", "America/Chicago", "15:50"),
            (datetime(2026, 11, 2, 19, 30, tzinfo=timezone.utc),
             "30 13 * * 1-5", "20:30", "America/Chicago", "20:30"),
        ]
        for now, cron, logical, zone, rome_time in cases:
            with self.subTest(now=now, cron=cron):
                d = decision(now, event_cron=cron)
                self.assertTrue(d["run"])
                self.assertEqual(d["slot"], logical)
                self.assertEqual(d["time_zone"], zone)
                self.assertEqual(d["rome"].strftime("%H:%M"), rome_time)

    def test_wrong_chicago_slot_or_delay_does_not_backdate_snapshot(self):
        wrong = decision(datetime(2026, 10, 30, 14, 50,
                                  tzinfo=timezone.utc),
                         event_cron="50 8 * * 1-5")
        self.assertFalse(wrong["run"])
        late = decision(datetime(2026, 10, 30, 14, 5,
                                 tzinfo=timezone.utc),
                        event_cron="50 8 * * 1-5")
        self.assertFalse(late["run"])
        manual = decision(datetime(2026, 10, 31, 15, 20,
                                   tzinfo=timezone.utc),
                          requested="20:30", manual=True)
        self.assertEqual(manual["slot"], "manuale")

    def test_original_gamma_json_quality_and_root(self):
        for instrument in ("NDX", "GLD", "USO"):
            with self.subTest(instrument=instrument):
                data = validate_options(instrument, synthetic(instrument))
                self.assertEqual(data["contratti_gamma_completi"], 4)
        with self.assertRaises(ValueError):
            validate_options("GLD", synthetic("USO"))

    def test_lacks_rights_does_not_connect_or_fake_downloads(self):
        def never_connect(*args):
            raise AssertionError("No download allowed when no rights.")
        with tempfile.TemporaryDirectory() as tmp:
            result = run_capture(
                now=datetime(2026, 10, 29, 13, 50, tzinfo=timezone.utc),
                env={}, output=Path(tmp), downloader=never_connect)
            self.assertEqual(result["status"], "PARZIALE_O_NON_CONFIGURATO")
            self.assertTrue(all(x["status"] == "NON_CONFIGURATO"
                                for x in result["markets"].values()))
            self.assertEqual(len(list(Path(tmp).glob("*.enc"))), 0)

    def test_encrypted_output_contains_original_chain_not_plaintext(self):
        key = Fernet.generate_key().decode()
        def mock_download(url, token):
            return synthetic(url.rsplit("/", 1)[-1])
        env = {
            "V2_AUTHORIZED_FEED_CONFIRMED": "true",
            "V2_ARCHIVE_FERNET_KEY": key,
            **{f"V2_FEED_{m}_URL": f"https://licensed.example.org/{m}"
               for m in ("NDX","GLD","USO")},
        }
        with tempfile.TemporaryDirectory() as tmp:
            result = run_capture(
                now=datetime(2026, 10, 29, 13, 50, tzinfo=timezone.utc),
                env=env, output=Path(tmp), downloader=mock_download)
            self.assertEqual(result["status"], "TUTTI_ARCHIVIATI")
            for m in ("NDX", "GLD", "USO"):
                self.assertEqual(result["markets"][m]["status"], "SCARICATO_CIFRATO")
                encrypted = (Path(tmp) / result["markets"][m]["file"]).read_bytes()
                self.assertNotIn(b"open_interest", encrypted)
                original = gzip.decompress(Fernet(key.encode()).decrypt(encrypted))
                self.assertEqual(json.loads(original)["symbol"],
                                 "_NDX" if m == "NDX" else m)

    def test_direct_cboe_urls_match_existing_manual_downloaders(self):
        from data_sources import NDX_URL
        from gld_cboe import GLD_URL
        from uso_cboe import USO_URL
        self.assertEqual(CBOE_PUBLIC_URLS,
                         {"NDX": NDX_URL, "GLD": GLD_URL, "USO": USO_URL})
        for url in CBOE_PUBLIC_URLS.values():
            self.assertEqual(safe_url(url), url)
        with self.assertRaisesRegex(ValueError, "diverso"):
            safe_url("https://cdn.cboe.com/api/global/delayed_quotes/options/SPX.json")

    def test_direct_cboe_3_markets_encrypted_without_manual_feed_urls(self):
        key = Fernet.generate_key().decode()
        calls = []
        def mock_download(url, token):
            self.assertEqual(token, "")
            calls.append(url)
            market = next(m for m, path in CBOE_PUBLIC_URLS.items()
                          if path == url)
            return synthetic(market)
        with tempfile.TemporaryDirectory() as tmp:
            result = run_capture(
                now=datetime(2026, 10, 29, 13, 50, tzinfo=timezone.utc),
                env={"V2_ARCHIVE_FERNET_KEY": key}, output=Path(tmp),
                downloader=mock_download)
            self.assertEqual(result["status"], "TUTTI_ARCHIVIATI")
            self.assertEqual(calls, list(CBOE_PUBLIC_URLS.values()))
            for market in CBOE_PUBLIC_URLS:
                m = result["markets"][market]
                self.assertEqual(m["source"], "CBOE_PUBLIC_CDN")
                self.assertEqual(m["status"], "SCARICATO_CIFRATO")
                encrypted = (Path(tmp)/m["file"]).read_bytes()
                original = gzip.decompress(Fernet(key.encode()).decrypt(encrypted))
                self.assertEqual(json.loads(original)["symbol"].lstrip("_"), market)

    def test_absent_encryption_secret_never_downloads_public_cboe(self):
        def block(*args, **kwargs):
            raise AssertionError("No Cboe GET without private encryption key")
        with tempfile.TemporaryDirectory() as tmp:
            report = run_capture(
                now=datetime(2026, 10, 29, 13, 50, tzinfo=timezone.utc),
                env={}, output=Path(tmp), downloader=block)
        self.assertTrue(all(x["status"] == "NON_CONFIGURATO"
                            for x in report["markets"].values()))
        self.assertTrue(all("V2_ARCHIVE_FERNET_KEY" in x.get("reason", "")
                            for x in report["markets"].values()))

    def test_direct_fetch_stops_on_access_denial_without_retry(self):
        class FakeResponse:
            def __init__(self, url, status):
                self.url, self.status_code = url, status
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def raise_for_status(self):
                pass
            def iter_content(self, chunk_size=0):
                raise AssertionError("Should not stream blocked response")
        for code in (401, 403, 429):
            calls = []
            def get(url, **kwargs):
                calls.append(url)
                return FakeResponse(url, code)
            with self.subTest(code=code):
                with self.assertRaisesRegex(RuntimeError, f"HTTP {code}"):
                    fetch_authorized(CBOE_PUBLIC_URLS["GLD"], get=get)
                self.assertEqual(len(calls), 1)

    def test_keeps_custom_feed_authorization_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            def forbidden(*a):
                raise AssertionError("Custom feed not authorized")
            result = run_capture(
                now=datetime(2026, 10, 29, 13, 50, tzinfo=timezone.utc),
                env={"V2_ARCHIVE_FERNET_KEY": Fernet.generate_key().decode(),
                     "V2_FEED_NDX_URL": "https://licensed.example.org/NDX"},
                output=Path(tmp), downloader=forbidden)
            self.assertEqual(result["markets"]["NDX"]["status"], "NON_CONFIGURATO")
            self.assertIn("consenso", result["markets"]["NDX"]["reason"])


if __name__ == "__main__":
    unittest.main()
