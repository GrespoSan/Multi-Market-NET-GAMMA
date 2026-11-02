"""No network. Shared Massive Futures temp cache, Rome-midnight disposal."""
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zoneinfo import ZoneInfo
import os
import unittest

import requests
from v2_massive_day_cache import fetch_json, purge_expired, invalidate_ratio_sessions


class DummyResponse:
    def __init__(self, payload=None, status=200):
        self.payload = payload
        self.status_code = status
        self.headers = {}
    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code), response=self)
    def json(self):
        return self.payload


class MassiveDayCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {"V2_MASSIVE_CACHE_DIR":self.tmp.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.url = "https://api.massive.com/futures/v1/aggs/CLZ6"
        self.params = {"resolution":"1session", "window_start.lte":"2026-10-30",
                       "limit":9}
        self.valid = {"status":"OK", "results":[
            {"ticker":"CLZ6","session_end_date":"2026-10-30","volume":199541}]}

    def test_same_verified_response_reused_across_separate_calls(self):
        seen=[]
        def getter(url,**kwargs):
            seen.append(url)
            return DummyResponse(self.valid)
        with patch("v2_massive_day_cache.requests.get", side_effect=getter):
            a=fetch_json(self.url, self.params, "secretA")
            b=fetch_json(self.url, self.params, "secretA")
            self.assertEqual(len(seen),1)
            self.assertEqual(a,b)
            self.assertEqual(a["results"][0]["volume"],199541)
            # No raw key in private SQLite data.
            files=list(Path(self.tmp.name).glob("massive-*.sqlite3"))
            self.assertEqual(len(files),1)
            self.assertNotIn(b"secretA", files[0].read_bytes())

    def test_api_key_contract_and_query_are_isolated(self):
        seen=[]
        def getter(url,**kwargs):
            seen.append(url)
            return DummyResponse(self.valid)
        with patch("v2_massive_day_cache.requests.get", side_effect=getter):
            fetch_json(self.url, self.params, "key-A")
            fetch_json(self.url, self.params, "key-B")
            fetch_json(self.url.replace("CLZ6","CLF7"), self.params, "key-A")
            self.assertEqual(len(seen),3)

    def test_failed_incomplete_or_empty_responses_not_cached(self):
        n=[0]
        def getter(url,**kwargs):
            n[0]+=1
            if n[0]==1: return DummyResponse(status=429)
            if n[0]==2: return DummyResponse({"status":"OK",
                "results":[{"ticker":"CLZ6"}],"next_url":"https://example.invalid"})
            if n[0]==3: return DummyResponse({"status":"OK","results":[]})
            return DummyResponse(self.valid)
        with patch("v2_massive_day_cache.requests.get", side_effect=getter):
            with self.assertRaises(requests.HTTPError):
                fetch_json(self.url, self.params, "secretA")
            self.assertIsNotNone(fetch_json(self.url, self.params, "secretA").get("next_url"))
            self.assertEqual(fetch_json(self.url, self.params, "secretA")["results"],[])
            self.assertEqual(fetch_json(self.url, self.params, "secretA"),self.valid)
            self.assertEqual(fetch_json(self.url, self.params, "secretA"),self.valid)
        self.assertEqual(n[0],4)

    def test_stale_files_deleted_next_rome_day_only_inside_cache_directory(self):
        a=Path(self.tmp.name)/"massive-20261102.sqlite3"
        b=Path(self.tmp.name)/"massive-20261103.sqlite3"
        unrelated=Path(self.tmp.name)/"CBOE_USO_20261102.json.gz.enc"
        for f in (a,b,unrelated):f.write_bytes(b"old")
        purge_expired(datetime(2026,11,3,1,tzinfo=ZoneInfo("Europe/Rome")))
        self.assertFalse(a.exists())
        self.assertTrue(b.exists())
        self.assertTrue(unrelated.exists())

    def test_new_day_unfreezes_ratios_but_retains_original_snapshots(self):
        state={
            "_v2_massive_session_rome_day":"2026-11-02",
            "uso_ratio_locked":{"ratio":0.6},
            "gld_ratio_tried":"abc",
            "ndx_basis_result":{"basis":140},
            "uso_cboe_raw":b"Cboe source",
            "v2_archive_choice_uso":"ultimo",
        }
        changed=invalidate_ratio_sessions(
            state,datetime(2026,11,3,0,1,tzinfo=ZoneInfo("Europe/Rome")))
        self.assertTrue(changed)
        for key in ("uso_ratio_locked","gld_ratio_tried","ndx_basis_result"):
            self.assertNotIn(key,state)
        self.assertEqual(state["uso_cboe_raw"],b"Cboe source")
        self.assertEqual(state["v2_archive_choice_uso"],"ultimo")
        self.assertFalse(invalidate_ratio_sessions(
            state,datetime(2026,11,3,10,tzinfo=ZoneInfo("Europe/Rome"))))

    def test_injected_market_data_getter_bypasses_persistent_cache(self):
        calls=[]
        def injected(url,**kwargs):
            calls.append(url)
            return DummyResponse(self.valid)
        fetch_json(self.url,self.params,"secretA",get=injected)
        fetch_json(self.url,self.params,"secretA",get=injected)
        self.assertEqual(len(calls),2)
        self.assertEqual(list(Path(self.tmp.name).glob("massive-*.sqlite3")), [])


if __name__=="__main__":
    unittest.main()
