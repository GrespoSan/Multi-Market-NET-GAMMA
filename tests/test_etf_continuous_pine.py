"""Continuous Pine exported without Massive or invented synchronized ETF/future ratio."""
import gzip
import json
import unittest
from datetime import date

from etf_future_pine import make_etf_future_pine
from v2_emergency_pine import build_current_pine

DAY=date(2026,11,4)
FRIDAY=date(2026,11,6)


def group(day, base):
    return {"expiry":day.isoformat(), "usable":True,
            "rows":[{"strike":float(base+i),"net":(-1.)**i*(i+1)*.14}
                    for i in range(3)]}


def cb_file(symbol):
    base = 359 if symbol=="GLD" else 158
    options=[]
    for expiry in (DAY,FRIDAY):
        for strike in (base-1,base,base+1):
            for cp in ("C","P"):
                options.append({
                    "option":f"{symbol}{expiry:%y%m%d}{cp}{strike*1000:08d}",
                    "open_interest":100 if cp=="C" else 70,
                    "gamma":0.01, "volume":5,
                })
    return json.dumps({
        "symbol":symbol, "timestamp":"2026-11-04 14:50:14",
        "data":{"current_price":base+1,"prev_day_close":base,
                "options":options},
    }).encode()


class ContinuousPineTests(unittest.TestCase):
    def test_both_continuous_future_pines_are_independent_of_massive(self):
        for symbol,ticker,base in (("GLD","COMEX:GC1!",359),
                                   ("USO","NYMEX:CL1!",158)):
            with self.subTest(symbol=symbol):
                rows={"0DTE":group(DAY,base),"Weekly":group(FRIDAY,base)}
                code=make_etf_future_pine(
                    symbol,rows,float(base),DAY,"CONTINUO",None,
                    continuous=True)
                self.assertIn("//@version=6",code)
                self.assertIn('string contractTicker = ticker.standard(syminfo.tickerid)',code)
                self.assertIn(f'ticker.standard(syminfo.tickerid) == "{ticker}"',code)
                micro = ("COMEX_MINI:MGC1!" if symbol == "GLD" else "NYMEX:MCL1!")
                self.assertIn(f'ticker.standard(syminfo.tickerid) == "{micro}"',code)
                self.assertIn('modeRatio = "Dinamico"',code)
                self.assertIn("float lockedRatio = na",code)
                self.assertIn("float ratioToDraw = dynamicAvailable ? lastDynamicRatio : na",code)
                self.assertIn("if barstate.islast and validTicker and not na(ratioToDraw)",code)
                self.assertIn("if barstate.islast and validTicker and na(ratioToDraw)",code)
                self.assertIn("etfTime == futTime",code)
                self.assertIn("close[1], time[1]",code)
                self.assertIn("lookahead=barmerge.lookahead_on",code)
                self.assertIn("timeframe.in_seconds() <= 300",code)
                self.assertIn('plot(ratioToDraw, title="Rapporto ETF/future"',code)
                self.assertNotIn("@FUT_TV@",code)
                self.assertNotIn("@RATIO_",code)
                self.assertNotIn("float lockedRatio = 1",code)
                self.assertIn(f'{base}.0',code)
                self.assertIn("array.push(resultLevels, etfStrike * ratio)",code)
                self.assertNotIn("syminfo.root == \"MGC\"",code)
                self.assertEqual(rows["0DTE"]["rows"][0]["strike"],float(base))
                self.assertEqual(rows["0DTE"]["rows"][0]["net"],.14)

    def test_reject_wrong_mode_or_incomplete_gamma(self):
        for symbol in ("GLD","USO"):
            base=359 if symbol=="GLD" else 158
            g={"0DTE":group(DAY,base)}
            with self.assertRaisesRegex(ValueError,"rapporto"):
                make_etf_future_pine(symbol,g,base,DAY,"test",None)
            with self.assertRaisesRegex(ValueError,"non inserire"):
                make_etf_future_pine(
                    symbol,g,base,DAY,"test",{"etf_symbol":symbol},continuous=True)
            broken={"0DTE":{**group(DAY,base),"usable":False}}
            with self.assertRaisesRegex(ValueError,"non completo"):
                make_etf_future_pine(symbol,broken,base,DAY,"test",None,continuous=True)

    def test_emergency_builds_continuous_without_conversion(self):
        for symbol,ticker in (("GLD","COMEX:GC1!"),("USO","NYMEX:CL1!")):
            with self.subTest(symbol=symbol):
                base=359 if symbol=="GLD" else 158
                raw=gzip.compress(cb_file(symbol))
                result=build_current_pine(symbol,raw,DAY,base,None)
                self.assertFalse(result["projected"])
                self.assertEqual(result["factor"],1.)
                self.assertEqual(set(result["profiles"]),{"0DTE","Weekly"})
                self.assertIn(ticker,result["pine"])
                self.assertIn("CONTINUO",result["pine"])
                self.assertEqual(result["symbol"],symbol)

    def test_main_archive_download_button_does_not_depend_on_ratio(self):
        from pathlib import Path
        base=Path(__file__).resolve().parent.parent
        view=(base/"etf_pine_view.py").read_text(encoding="utf-8")
        emergency=(base/"v2_emergency_pine.py").read_text(encoding="utf-8")
        self.assertIn('script = make_etf_future_pine(',view)
        self.assertNotIn("snapshot_token",view)
        self.assertNotIn("fetch_oil_pair(",view)
        self.assertIn('continuous=True',view)
        self.assertIn('continuous=True',emergency)
        self.assertIn('projected=result["projected"]',emergency)
        self.assertIn('NET GAMMA CONTINUO GC1!/MGC1! o CL1!/MCL1!',emergency)


if __name__=="__main__":
    unittest.main()
