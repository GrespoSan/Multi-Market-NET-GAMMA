"""No market connectivity required: verify exact 5-minute time matching."""
import unittest
from datetime import date, datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from future_ratio import (choose_contract, synchronized_pair, manual_pair,
                          fetch_pair)

DAY = date(2026, 10, 29)


def bars(*pairs):
    idx = pd.DatetimeIndex([t for t, _ in pairs], tz="UTC")
    return pd.DataFrame({"Close": [c for _, c in pairs]}, index=idx)


def t(hour, minute):
    return datetime(2026, 10, 29, hour, minute, tzinfo=timezone.utc)


class RatioTests(unittest.TestCase):
    def test_exact_timestamp_pair_and_lock_data(self):
        etf = bars((t(18, 0), 368.10), (t(18, 5), 368.36),
                   (t(18, 10), 368.50))
        fut = bars((t(18, 0), 4069.1), (t(18, 5), 4070.1),
                   (t(18, 15), 4080.0))
        result = synchronized_pair(
            etf, fut, "GLD", "GCZ26.CMX", "COMEX:GCZ2026",
            DAY, now=t(18, 20))
        self.assertEqual(result["bar_utc"], t(18, 5).isoformat(timespec="seconds"))
        self.assertEqual(result["etf_price"], 368.36)
        self.assertEqual(result["future_price"], 4070.1)
        self.assertAlmostEqual(result["ratio"], 4070.1/368.36)
        self.assertEqual(result["future_tv_symbol"], "COMEX:GCZ2026")

    def test_stale_bar_while_etf_open_rejected(self):
        a = bars((t(13, 35), 370.))
        b = bars((t(13, 35), 4050.))
        # 16:30 UTC = 12:30 NY, last common bar is almost 3 hours ago.
        with self.assertRaisesRegex(ValueError, "troppo vecchie"):
            synchronized_pair(a,b,"GLD","GCZ26.CMX","COMEX:GCZ2026",
                              DAY, now=t(16, 30))

    def test_unfinished_and_outside_regular_hours_rejected(self):
        a = bars((t(19, 55), 369.))
        b = bars((t(19, 55), 4100.))
        with self.assertRaisesRegex(ValueError, "Nessuna coppia"):
            synchronized_pair(a,b,"GLD","GCZ26.CMX","COMEX:GCZ2026",
                              DAY,now=t(19, 57))
        a = bars((t(20, 30), 369.))
        b = bars((t(20, 30), 4100.))
        with self.assertRaisesRegex(ValueError, "Nessuna coppia"):
            synchronized_pair(a,b,"GLD","GCZ26.CMX","COMEX:GCZ2026",
                              DAY,now=t(20, 50))

    def test_mismatched_timestamp_never_nearest_neighbor(self):
        etf = bars((t(18, 5), 368.36))
        fut = bars((t(18, 10), 4070.1))
        with self.assertRaisesRegex(ValueError, "Nessuna coppia"):
            synchronized_pair(etf,fut,"GLD","GCZ26.CMX","COMEX:GCZ2026",
                              DAY,now=t(18, 20))

    def test_invalid_or_na_prices_rejected(self):
        a = bars((t(18, 5), 0.0))
        b = bars((t(18, 5), 4070.1))
        with self.assertRaisesRegex(ValueError, "Nessuna coppia"):
            synchronized_pair(a,b,"GLD","GCZ26.CMX","COMEX:GCZ2026",
                              DAY,now=t(18, 20))


    def test_gold_early_morning_capture_uses_prior_common_completed_session(self):
        # Nov 2 at 07:31 Rome = Nov 2 01:31 NY, before GLD trading.
        from future_ratio import fetch_gold_pair
        capture=datetime(2026,11,2,7,31,tzinfo=ZoneInfo("Europe/Rome"))
        cash=pd.date_range("2026-10-30T13:30:00Z",periods=78,freq="5min")
        future_after=pd.Timestamp("2026-11-02T14:35:00Z")
        class FakeTicker:
            def history(self, **kwargs):
                self_kwargs=kwargs
                return bars(*[(ts.to_pydatetime(),355.0+i*.01)
                              for i,ts in enumerate(cash)],
                            (future_after.to_pydatetime(),380))
        class FakeYahoo:
            def Ticker(self, name):
                if name != "GLD":
                    raise AssertionError("Gold futures must come from Massive")
                return FakeTicker()
        def getter(url, params=None, headers=None, timeout=None):
            self.assertTrue(url.endswith("/GCZ6"))
            self.assertEqual(params["resolution"],"5min")
            self.assertEqual(params["window_start.gte"],"2026-10-30")
            self.assertEqual(params["window_start.lt"],"2026-10-31")
            self.assertEqual(headers["Authorization"],"Bearer sample")
            rows=[{
                "ticker":"GCZ6","session_end_date":"2026-10-30",
                "window_start":int(ts.value),"close":3890.0+i*.03
            } for i,ts in enumerate(cash)]
            return type("Reply",(),{"raise_for_status":lambda self:None,
                                    "json":lambda self:{"status":"OK","results":rows}})()
        result=fetch_gold_pair("GCZ26 · dicembre 2026",capture,"sample",
                               yf_module=FakeYahoo(),get=getter)
        self.assertEqual(result["target_date"],"2026-10-30")
        self.assertEqual(result["future_massive_ticker"],"GCZ6")
        self.assertEqual(result["bar_ny"][:10],"2026-10-30")
        self.assertEqual(result["bar_ny"][11:16],"15:55")
        self.assertAlmostEqual(result["ratio"],(3890+77*.03)/(355+77*.01))
        self.assertIn("Massive GCZ6",result["source"])

    def test_gold_never_uses_post_capture_prices_or_fake_continuous(self):
        from future_ratio import fetch_gold_pair
        capture=datetime(2026,11,2,7,31,tzinfo=ZoneInfo("Europe/Rome"))
        future_time=datetime(2026,11,2,14,35,tzinfo=timezone.utc)
        class OnlyFuture:
            def history(self,**kwargs):
                return bars((future_time,375.0))
        class FakeYahoo:
            def Ticker(self,ticker):
                if ticker != "GLD":
                    raise AssertionError("Gold futures must not be read from Yahoo")
                return OnlyFuture()
        with self.assertRaisesRegex(ValueError,"Nessuna seduta GLD"):
            fetch_gold_pair("GCZ26 · dicembre 2026",capture,"sample",
                            yf_module=FakeYahoo(),
                            get=lambda *a,**k:self.fail("Massive must not be read"))


    def test_oil_early_morning_archive_uses_previous_cash_session_and_exact_contract(self):
        from future_ratio import fetch_oil_pair
        capture=datetime(2026,11,2,7,31,tzinfo=ZoneInfo("Europe/Rome"))
        cash=pd.date_range("2026-10-30T13:30:00Z",periods=78,freq="5min")
        future_after=pd.Timestamp("2026-11-02T14:35:00Z")
        class FakeTicker:
            def history(self,**kwargs):
                return bars(*[(ts.to_pydatetime(),168+i*.01)
                              for i,ts in enumerate(cash)],
                            (future_after.to_pydatetime(),181))
        class FakeYahoo:
            def Ticker(self,name):
                if name!="USO":
                    raise AssertionError("No continuous or dated Yahoo CL")
                return FakeTicker()
        def getter(url,params=None,headers=None,timeout=None):
            self.assertTrue(url.endswith("/CLZ6"))
            self.assertEqual(params["resolution"],"5min")
            self.assertEqual(params["window_start.gte"],"2026-10-30")
            self.assertEqual(params["window_start.lt"],"2026-10-31")
            self.assertEqual(headers["Authorization"],"Bearer test-token")
            rows=[{"ticker":"CLZ6","session_end_date":"2026-10-30",
                   "window_start":int(ts.value),"close":103+i*.002}
                  for i,ts in enumerate(cash)]
            return type("Reply",(),{"raise_for_status":lambda self:None,
                                    "json":lambda self:{"status":"OK","results":rows}})()
        result=fetch_oil_pair("CLZ26 · dicembre 2026",capture,"test-token",
                              yf_module=FakeYahoo(),get=getter)
        self.assertEqual(result["target_date"],"2026-10-30")
        self.assertEqual(result["future_massive_ticker"],"CLZ6")
        self.assertEqual(result["bar_ny"][:10],"2026-10-30")
        self.assertEqual(result["bar_ny"][11:16],"15:55")
        self.assertAlmostEqual(result["ratio"],(103+77*.002)/(168+77*.01))
        self.assertIn("Massive CLZ6",result["source"])
        self.assertEqual(result["future_tv_symbol"],"NYMEX:CLZ2026")

    def test_oil_selected_next_month_really_changes_massive_contract(self):
        from future_ratio import fetch_oil_pair
        capture=datetime(2026,11,2,7,31,tzinfo=ZoneInfo("Europe/Rome"))
        cash=pd.date_range("2026-10-30T19:45:00Z",periods=3,freq="5min")
        class FakeYahoo:
            def Ticker(self,name):
                if name!="USO": raise AssertionError("Wrong ticker")
                return type("Quotes",(),{"history":lambda self,**k:bars(
                    *[(d.to_pydatetime(),168.) for d in cash])})()
        def getter(url,**kwargs):
            self.assertTrue(url.endswith("/CLF7"))
            self.assertEqual(kwargs["params"]["window_start.lt"],"2026-10-31")
            rows=[{"ticker":"CLF7","session_end_date":"2026-10-30",
                   "window_start":int(d.value),"close":101.}
                  for d in cash]
            return type("Reply",(),{"raise_for_status":lambda self:None,
                                    "json":lambda self:{"status":"OK","results":rows}})()
        result=fetch_oil_pair("CLF27 · gennaio 2027",capture,"test-token",
                              yf_module=FakeYahoo(),get=getter)
        self.assertEqual(result["future_massive_ticker"],"CLF7")
        self.assertEqual(result["future_tv_symbol"],"NYMEX:CLF2027")

    def test_oil_rejects_post_capture_data_and_missing_key(self):
        from future_ratio import fetch_oil_pair
        capture=datetime(2026,11,2,7,31,tzinfo=ZoneInfo("Europe/Rome"))
        stamp=datetime(2026,11,2,14,35,tzinfo=timezone.utc)
        class OnlyFuture:
            def history(self,**kw):
                return bars((stamp,170.))
        class FakeYahoo:
            def Ticker(self,name):
                if name!="USO": raise AssertionError("Wrong ticker")
                return OnlyFuture()
        with self.assertRaisesRegex(ValueError,"Nessuna seduta USO"):
            fetch_oil_pair("CLZ26 · dicembre 2026",capture,"test-token",
                           yf_module=FakeYahoo(),
                           get=lambda *a,**k:self.fail("Must not call Massive"))
        # With an eligible past ETF bar, the missing Massive key must
        # fail closed before issuing any request or inventing a CL price.
        previous=datetime(2026,10,30,19,55,tzinfo=timezone.utc)
        class PriorOnly:
            def history(self,**kw):
                return bars((previous,168.8))
        class PriorYahoo:
            def Ticker(self,name):
                if name!="USO": raise AssertionError("Unexpected futures fallback")
                return PriorOnly()
        with self.assertRaisesRegex(ValueError,"MASSIVE_API_KEY"):
            fetch_oil_pair("CLZ26 · dicembre 2026",capture,"",
                           yf_module=PriorYahoo(),
                           get=lambda *a,**k:self.fail("Must not call Massive"))


    def test_automatic_oil_roll_uses_last_completed_session_volumes(self):
        from future_ratio import fetch_oil_pair, AUTO_OIL_CONTRACT
        capture=datetime(2026,11,2,7,31,tzinfo=ZoneInfo("Europe/Rome"))
        cash=pd.date_range("2026-10-30T13:30:00Z",periods=78,freq="5min")
        class FakeYahoo:
            def Ticker(self,ticker):
                if ticker != "USO": raise AssertionError("Unexpected Yahoo future")
                return type("Quotes",(),{"history":lambda self,**kw:bars(
                    *[(t.to_pydatetime(),168+.01*i) for i,t in enumerate(cash)])})()
        class Response:
            def __init__(self,data): self.data=data
            def raise_for_status(self): return None
            def json(self): return self.data
        def contract(name,expiration):
            return {"ticker":name,"product_code":"CL","active":True,
                    "type":"single","first_trade_date":"2025-01-01",
                    "last_trade_date":expiration}
        expiry=[contract("CLF7","2026-12-21"),contract("CLZ6","2026-11-20")]
        def make_get(volumes):
            def getter(url,params=None,headers=None,timeout=None):
                self.assertEqual(headers["Authorization"],"Bearer secret")
                if url.endswith("/contracts"):
                    self.assertEqual(params["date"],"2026-10-30")
                    return Response({"status":"OK","results":expiry})
                contract_name=url.rsplit("/",1)[-1]
                if params["resolution"]=="1session":
                    self.assertEqual(params["window_start.lte"],"2026-10-30")
                    return Response({"status":"OK","results":[{
                        "ticker":contract_name,"session_end_date":"2026-10-30",
                        "volume":volumes[contract_name]}]})
                self.assertEqual(params["resolution"],"5min")
                self.assertEqual(params["window_start.lt"],"2026-10-31")
                return Response({"status":"OK","results":[{
                    "ticker":contract_name,"session_end_date":"2026-10-30",
                    "window_start":int(t.value),
                    "close":103+.002*i if contract_name=="CLZ6" else 101+.002*i}
                    for i,t in enumerate(cash)]})
            return getter
        # Before CL roll: front has more volume.
        front=fetch_oil_pair(AUTO_OIL_CONTRACT,capture,"secret",
                             yf_module=FakeYahoo(),
                             get=make_get({"CLZ6":199541,"CLF7":43594}))
        self.assertEqual(front["future_massive_ticker"],"CLZ6")
        self.assertEqual(front["future_tv_symbol"],"NYMEX:CLZ2026")
        self.assertEqual(front["auto_contract"]["reference_date"],"2026-10-30")
        self.assertAlmostEqual(front["ratio"],(103+.002*77)/(168+.01*77))
        # Once the next contract overtakes front, auto selects the next.
        next_month=fetch_oil_pair(AUTO_OIL_CONTRACT,capture,"secret",
                                 yf_module=FakeYahoo(),
                                 get=make_get({"CLZ6":43594,"CLF7":199541}))
        self.assertEqual(next_month["future_massive_ticker"],"CLF7")
        self.assertEqual(next_month["future_tv_symbol"],"NYMEX:CLF2027")
        self.assertEqual(next_month["auto_contract"]["second_volume"],199541)

    def test_automatic_oil_roll_fails_closed_on_unverified_volume(self):
        from future_ratio import _auto_oil_contract
        class Response:
            def __init__(self,data): self.data=data
            def raise_for_status(self): return None
            def json(self): return self.data
        contracts=[
            {"ticker":t,"product_code":"CL","active":True,"type":"single",
             "first_trade_date":"2025-01-01","last_trade_date":d}
            for t,d in (("CLZ6","2026-11-20"),("CLF7","2026-12-21"))
        ]
        def getter(url,**kwargs):
            if url.endswith("/contracts"):
                return Response({"status":"OK","results":contracts})
            return Response({"status":"OK","results":[]})
        with self.assertRaisesRegex(ValueError,"volumi della stessa seduta"):
            _auto_oil_contract(date(2026,10,30),"secret",get=getter)
        with self.assertRaisesRegex(ValueError,"MASSIVE_API_KEY"):
            _auto_oil_contract(date(2026,10,30),"",get=getter)

    def test_oil_auto_ui_default_and_gold_logic_preserved(self):
        from pathlib import Path
        content=(Path(__file__).resolve().parent.parent/"etf_pine_view.py").read_text()
        self.assertIn("[AUTO_OIL_CONTRACT] + list(CONTRACTS[symbol]",content)
        self.assertIn('st.session_state["uso_ratio_contract"] = AUTO_OIL_CONTRACT',content)
        self.assertIn("pair = fetch_gold_pair(selected, capture_dt, api_key)",content)
        self.assertIn("pair = fetch_oil_pair(selected, capture_dt, api_key)",content)
        self.assertIn("actual_contract = result",content)


    def test_cached_oil_rollover_survives_429_on_last_request(self):
        """A 429 on the fourth Massive call must not redownload prior three."""
        import future_ratio as fr
        from unittest.mock import patch
        import requests

        capture=datetime(2026,11,2,7,31,tzinfo=ZoneInfo("Europe/Rome"))
        cash=pd.date_range("2026-10-30T19:50:00Z",periods=2,freq="5min")

        class FakeYahoo:
            def Ticker(self,name):
                self.assert_us_oil(name)
                return type("Frame",(),{"history":lambda self,**kwargs:bars(
                    *[(d.to_pydatetime(),168.7) for d in cash])})()
            @staticmethod
            def assert_us_oil(name):
                if name!="USO":
                    raise AssertionError("No fallback to Yahoo CL")

        class Reply:
            def __init__(self,payload=None,status=200):
                self.payload=payload
                self.status_code=status
                self.headers={"Retry-After":"60"} if status==429 else {}
            def raise_for_status(self):
                if self.status_code>=400:
                    raise requests.HTTPError(
                        f"{self.status_code}",response=self)
            def json(self):
                return self.payload

        contracts=[
            {"ticker":t,"product_code":"CL","active":True,"type":"single",
             "first_trade_date":"2025-01-01","last_trade_date":d}
            for t,d in (("CLZ6","2026-11-20"),("CLF7","2026-12-21"))
        ]
        calls=[]
        def getter(url,params=None,headers=None,timeout=None):
            calls.append((url,params["resolution"] if "resolution" in params else "contracts"))
            if url.endswith("/contracts"):
                return Reply({"status":"OK","results":contracts})
            ticker=url.rsplit("/",1)[-1]
            if params["resolution"]=="1session":
                vol=199541 if ticker=="CLZ6" else 43594
                return Reply({"status":"OK","results":[{
                    "ticker":ticker,"volume":vol,"session_end_date":"2026-10-30"}]})
            self.assertEqual(ticker,"CLZ6")
            if sum(1 for _,res in calls if res=="5min")==1:
                return Reply(status=429)
            return Reply({"status":"OK","results":[{
                "ticker":ticker,"session_end_date":"2026-10-30",
                "window_start":int(d.value),"close":103.14}
                for d in cash]})

        fr._cl_cached_json.cache_clear()
        clock=[1000.]
        try:
            with patch.object(fr.requests,"get",side_effect=getter), \\
                 patch.object(fr,"monotonic",side_effect=lambda:clock[0]), \\
                 patch.object(fr,"_CL_COOLDOWN_UNTIL",0.):
                with self.assertRaisesRegex(ValueError,"HTTP 429"):
                    fr.fetch_oil_pair(fr.AUTO_OIL_CONTRACT,capture,
                                      "test-cache-429-key",yf_module=FakeYahoo())
                self.assertEqual(len(calls),4)
                with self.assertRaisesRegex(ValueError,"attendi almeno"):
                    fr.fetch_oil_pair(fr.AUTO_OIL_CONTRACT,capture,
                                      "test-cache-429-key",yf_module=FakeYahoo())
                self.assertEqual(len(calls),4)
                clock[0]+=61
                result=fr.fetch_oil_pair(fr.AUTO_OIL_CONTRACT,capture,
                                         "test-cache-429-key",yf_module=FakeYahoo())
                self.assertEqual(len(calls),5)
                self.assertEqual(result["future_massive_ticker"],"CLZ6")
                self.assertAlmostEqual(result["ratio"],103.14/168.7)
                self.assertEqual(result["bar_ny"][11:16],"15:55")
                # Another snapshot using the same completed ETF cash session:
                # zero additional Massive calls, and a frozen valid mapping.
                later=datetime(2026,11,2,9,5,tzinfo=ZoneInfo("Europe/Rome"))
                again=fr.fetch_oil_pair(fr.AUTO_OIL_CONTRACT,later,
                                        "test-cache-429-key",yf_module=FakeYahoo())
                self.assertEqual(len(calls),5)
                self.assertAlmostEqual(again["ratio"],result["ratio"])
        finally:
            fr._cl_cached_json.cache_clear()

    def test_cached_cl_responses_are_not_shared_with_injected_test_getters(self):
        import future_ratio as fr
        target=date(2026,10,30)
        calls=[]
        def getter(url,params=None,headers=None,timeout=None):
            calls.append(url)
            return type("Reply",(),{"raise_for_status":lambda self:None,
                   "json":lambda self:{"status":"OK","results":[{
                       "ticker":"CLZ6","session_end_date":target.isoformat(),
                       "window_start":int(pd.Timestamp("2026-10-30T19:55Z").value),
                       "close":103.14}]}})()
        first=fr._oil_massive_bars("CLZ6",target,"test-123",get=getter)
        second=fr._oil_massive_bars("CLZ6",target,"test-123",get=getter)
        self.assertEqual(len(calls),2)
        self.assertTrue(first.equals(second))

    def test_manual_pair_is_explicitly_unverified(self):
        pair = manual_pair(167.46, 101.14, "USO",
                           "CLZ26 · dicembre 2026", DAY, "14:45")
        self.assertAlmostEqual(pair["ratio"], 101.14/167.46)
        self.assertIn("NON verificata", pair["source"])
        self.assertEqual(pair["future_tv_symbol"], "NYMEX:CLZ2026")
        with self.assertRaises(ValueError):
            manual_pair(167.46,101.14,"USO",
                        "CLZ26 · dicembre 2026",DAY,"22:30")

    def test_chosen_contract_is_explicit(self):
        self.assertEqual(choose_contract("GLD", "GCZ26 · dicembre 2026"),
                         ("GCZ26.CMX", "COMEX:GCZ2026"))
        self.assertEqual(choose_contract("USO", "CLZ26 · dicembre 2026"),
                         ("CLZ26.NYM", "NYMEX:CLZ2026"))
        with self.assertRaisesRegex(ValueError, "Contratto"):
            choose_contract("USO","CL1!")

    def test_yfinance_never_silently_substitutes_continuous_future(self):
        class FakeTicker:
            def __init__(self, name):
                self.name = name
            def history(self, **kwargs):
                return bars((t(18, 0), 170. if self.name == "USO" else 101.))
        class FakeYahoo:
            used = []
            def Ticker(self, name):
                self.used.append(name)
                return FakeTicker(name)
        yahoo=FakeYahoo()
        pair=fetch_pair("USO", "CLZ26 · dicembre 2026",
                        DAY,now=t(18, 20),yf_module=yahoo)
        self.assertEqual(yahoo.used, ["USO", "CLZ26.NYM"])
        self.assertEqual(pair["future_tv_symbol"], "NYMEX:CLZ2026")


if __name__ == "__main__":
    unittest.main()
