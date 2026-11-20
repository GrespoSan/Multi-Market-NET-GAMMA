"""Hard no-network Cboe pause for scheduled and all manual Multi-Market feeds."""
import unittest
from unittest.mock import patch

import v2_cron
from data_sources import download_ndx
from gld_cboe import download_gld
from uso_cboe import download_uso
from v2_universal_cboe import download_once
from cboe_acquisition_pause import CBOE_ACQUISITIONS_PAUSED


class PauseTests(unittest.TestCase):
    def test_all_source_requests_block_before_http(self):
        self.assertTrue(CBOE_ACQUISITIONS_PAUSED)
        with patch("requests.get") as fake:
            for operation in (
                download_ndx, download_gld, download_uso,
                lambda: download_once("RUT"),
                lambda: download_once("DJX"),
                lambda: download_once("AAPL"),
                lambda: v2_cron.fetch_authorized(v2_cron.CBOE_PUBLIC_URLS["NDX"]),
            ):
                with self.subTest(operation=str(operation)):
                    with self.assertRaisesRegex(RuntimeError, "temporaneamente sospese"):
                        operation()
            fake.assert_not_called()

    def test_cron_stops_even_with_valid_slot(self):
        with patch.object(v2_cron, "fetch_authorized") as fake:
            result = v2_cron.run_capture()
            self.assertEqual(result["status"], "CBOE_PAUSED")
            self.assertEqual(result["markets"], {})
            fake.assert_not_called()

    def test_manual_import_remains(self):
        from pathlib import Path
        base = Path(__file__).resolve().parents[1]
        for filename in ("v2_emergency_pine.py", "v2_universal_cboe.py",
                         "v2_index_market_view.py"):
            source = (base / filename).read_text()
            self.assertIn("disabled=CBOE_ACQUISITIONS_PAUSED", source)
            self.assertIn("Usa file importato", source)


if __name__ == "__main__":
    unittest.main()
