"""GLD/USO: solo continui, prezzi M5 sincronizzati e Pine indipendenti da Massive."""
import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import unittest

import pandas as pd

from v2_continuous_ratio import (
    CONTINUOUS, last_closed_continuous_pair, active_snapshot_cutoff,
    load_chart_continuous_mapping,
)
from etf_future_pine import make_etf_future_pine

ROOT=Path(__file__).resolve().parents[1]
NY=ZoneInfo("America/New_York")


def bars(base, day=4, *, missing=None):
    # 09:30 NY Nov 4 = 14:30 UTC
    times=[datetime(2026,11,day,14,30,tzinfo=timezone.utc)+
           timedelta(minutes=5*j) for j in range(7)]
    vals=[base+i for i in range(len(times))]
    if missing is not None:
        times.pop(missing);vals.pop(missing)
    return pd.DataFrame({"Close":vals},index=pd.DatetimeIndex(times))


def profile():
    return {"usable":True,"expiry":"2026-11-04",
            "rows":[{"strike":159.,"net":-19.},{"strike":160.,"net":24.}]}


class TestContinuousOnly(unittest.TestCase):
    def test_last_two_closed_bars_same_timestamp_and_capture_guard(self):
        cutoff=datetime(2026,11,4,14,49,tzinfo=timezone.utc)
        for symbol,e,f,tv in (
            ("GLD",370.,4080.,"COMEX:GC1!"),
            ("USO",155.,95.,"NYMEX:CL1!"),
        ):
            with self.subTest(symbol=symbol):
                result=last_closed_continuous_pair(
                    symbol,bars(e),bars(f),cutoff,
                    now=datetime(2026,11,4,16,tzinfo=timezone.utc))
                # 14:40 bar closes 14:45. 14:45 bar closes 14:50 > cutoff.
                self.assertEqual(result["bar_ny"][:16],"2026-11-04T09:40")
                self.assertAlmostEqual(result["ratio"],(f+2)/(e+2))
                self.assertEqual(result["future_tv_symbol"],tv)
                self.assertEqual(result["mode"],"continuous-yahoo-5m")
                self.assertTrue(result["continuous_proxy"])

    def test_missing_common_bars_or_unverified_clock_never_fabricates(self):
        cutoff=datetime(2026,11,4,14,49,tzinfo=timezone.utc)
        only_today=bars(370.)
        tomorrow=bars(4070.,day=5)
        with self.assertRaisesRegex(ValueError,"Nessuna coppia M5"):
            last_closed_continuous_pair(
                "GLD",only_today,tomorrow,cutoff,
                now=datetime(2026,11,4,16,tzinfo=timezone.utc))
        with self.assertRaisesRegex(ValueError,"fuso"):
            last_closed_continuous_pair("USO",only_today,only_today,
                                        datetime(2026,11,4,14,49))
        with self.assertRaisesRegex(ValueError,"futuro"):
            last_closed_continuous_pair(
                "GLD",only_today,only_today,
                datetime(2026,11,4,16,tzinfo=timezone.utc),
                now=datetime(2026,11,4,15,tzinfo=timezone.utc))

    def test_verified_archive_time_only_and_no_upload_time_guessed(self):
        for sym in ("GLD","USO"):
            state={f"{sym.lower()}_cboe_source":"Archivio privato · rilevamento programmato",
                   f"v2_archive_capture_rome_{sym}":"2026-11-04T15:50:00+01:00"}
            self.assertEqual(active_snapshot_cutoff(sym,state),
                             "2026-11-04T15:50:00+01:00")
            def mock_loader(symbol, stamp):
                self.assertEqual(symbol,sym)
                self.assertEqual(stamp,state[f"v2_archive_capture_rome_{sym}"])
                return {"ratio":11 if symbol=="GLD" else .62}
            value,error=load_chart_continuous_mapping(sym,state,loader=mock_loader)
            self.assertIsNone(error)
            self.assertIsNotNone(value)
            state[f"{sym.lower()}_cboe_source"]="Importazione manuale"
            state[f"{sym.lower()}_cboe_import_rome"]="2026-11-04T15:50:00+01:00"
            self.assertIsNone(active_snapshot_cutoff(sym,state))
            v,reason=load_chart_continuous_mapping(sym,state,loader=mock_loader)
            self.assertIsNone(v)
            self.assertIsInstance(reason,str)

    def test_future_pine_from_real_gamma_without_futures_mapping(self):
        for sym in ("GLD","USO"):
            src=make_etf_future_pine(
                sym,{"0DTE":profile()},159.,datetime(2026,11,4).date(),
                "CONTINUO",None,continuous=True)
            self.assertIn("modeRatio = \"Dinamico\"",src)
            self.assertIn("and not na(ratioToDraw)",src)
            self.assertIn("etfTime == futTime",src)
            self.assertIn("ratioToDraw",src)
            self.assertNotIn("MASSIVE_API_KEY",src)
            self.assertNotIn("CLZ2026",src)
            self.assertNotIn("GCZ2026",src)

    def test_no_legacy_conversion_is_reachable_from_gl_or_uso_ui(self):
        pine=(ROOT/"etf_pine_view.py").read_text()
        self.assertNotIn("prepare_locked_chart_mapping",pine)
        self.assertNotIn("fetch_gold_pair(",pine)
        self.assertNotIn("fetch_oil_pair(",pine)
        self.assertNotIn("AUTO_OIL_CONTRACT",pine)
        self.assertNotIn("MASSIVE_API_KEY",pine)
        self.assertNotIn("Inserisci manualmente",pine)
        self.assertNotIn("Riprova calcolo",pine)
        for sym,view in (("GLD","gld_cboe_view.py"),("USO","uso_cboe_view.py")):
            s=(ROOT/view).read_text()
            ast.parse(s)
            self.assertIn('load_chart_continuous_mapping(',s)
            self.assertIn("if projected:",s)
            self.assertNotIn("prepare_locked_chart_mapping(",s)
            self.assertNotIn("Massive",s)
            self.assertNotIn("st.warning(\"Rapporto",s)
            self.assertIn('NET GAMMA '+("GC" if sym=="GLD" else "CL")+' CONTINUO',s)


if __name__=="__main__":
    unittest.main()
