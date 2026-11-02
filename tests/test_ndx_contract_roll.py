"""Contract-specific Nasdaq–NDX basis and CME quarterly automatic rollover.

No live network: fixture time series and fake Massive JSON.
"""
import unittest
from datetime import date
import pandas as pd

from ndx_basis import nq_contract_for_date, _dated_nq_bars, aligned_basis


class FakeResponse:
    def __init__(self, payload):
        self.payload=payload
    def raise_for_status(self):
        return None
    def json(self):
        return self.payload


class DateSpecificNasdaqBasisTests(unittest.TestCase):
    def test_rollover_december_2026_monday_and_march_2027(self):
        dec=nq_contract_for_date(date(2026,11,2))
        self.assertEqual(dec["ticker"],"NQZ6")
        self.assertEqual(dec["tv_symbol"],"NQZ2026")
        self.assertEqual(dec["roll_day"],date(2026,12,14))
        self.assertEqual(nq_contract_for_date(date(2026,12,11))["ticker"],"NQZ6")
        self.assertEqual(nq_contract_for_date(date(2026,12,14))["ticker"],"NQH7")
        self.assertEqual(nq_contract_for_date(date(2027,3,12))["ticker"],"NQH7")
        self.assertEqual(nq_contract_for_date(date(2027,3,15))["ticker"],"NQM7")

    def test_prior_cash_bars_from_named_contract_keep_15m_formula(self):
        reference=date(2026,10,30)
        utc=pd.date_range("2026-10-30 13:30:00+00:00",periods=26,freq="15min")
        rows=[{
            "ticker":"NQZ6","session_end_date":reference.isoformat(),
            "window_start":int(ts.value),"close":10000+i+135
        } for i,ts in enumerate(utc)]
        def getter(url,params=None,headers=None,timeout=None):
            self.assertTrue(url.endswith("/NQZ6"))
            self.assertEqual(params["resolution"],"15min")
            self.assertEqual(params["window_start.gte"],"2026-10-30")
            self.assertEqual(headers["Authorization"],"Bearer test-key")
            return FakeResponse({"status":"OK","results":rows})
        nq=_dated_nq_bars("NQZ6",reference,"test-key",get=getter)
        ndx=pd.Series([10000+i for i in range(26)],index=utc)
        result=aligned_basis(nq,ndx,date(2026,11,2))
        self.assertEqual(result["bar_count"],26)
        self.assertAlmostEqual(result["basis"],135,places=8)
        self.assertEqual(result["reference_date"],reference)

    def test_missing_key_never_fetches_or_falls_back_to_continuous(self):
        def unexpected(*args,**kwargs):
            self.fail("Network access must not be attempted without a key")
        with self.assertRaisesRegex(ValueError,"MASSIVE_API_KEY"):
            _dated_nq_bars("NQZ6",date(2026,10,30),"",get=unexpected)

    def test_previous_session_data_never_mix_future_sessions(self):
        reference=date(2026,10,30)
        t=pd.Timestamp("2026-10-30T13:30:00Z")
        rows=[
          {"ticker":"NQZ6","session_end_date":"2026-10-29",
           "window_start":int(t.value),"close":99999},
          {"ticker":"NQH7","session_end_date":"2026-10-30",
           "window_start":int(t.value),"close":88888},
          {"ticker":"NQZ6","session_end_date":"2026-10-30",
           "window_start":int(t.value),"close":10135},
        ]
        def getter(*args,**kwargs):
            return FakeResponse({"status":"OK","results":rows})
        series=_dated_nq_bars("NQZ6",reference,"test-key",get=getter)
        self.assertEqual(len(series),1)
        self.assertEqual(series.iloc[0],10135)


if __name__=="__main__":
    unittest.main()
