"""SPX-style time-snapshot Pine exports for V2. Synthetic data, no network."""
from datetime import date
from unittest.mock import patch
import unittest
from v2_pine_session import parse_archived_capture, compare_capture_pair
from v2_pine_timed_exports import produce_timed_scripts

DAY=date(2026,11,2)
FRIDAY=date(2026,11,6)
TIMES=(("0730","063100"),("1550","145100"),("2030","195100"))


def capture(symbol,slot,utc_time):
    filename=f"{symbol}_20261102T{utc_time}Z_{slot}_{'a'*12}.json.gz"
    return parse_archived_capture(filename,symbol,DAY)


def gamma_profile(symbol,base,expiry,net):
    if symbol=="NDX":
        return {"expiry":expiry.isoformat(),"band_pct":3.0,"rows":[
            {"strike_index":base,"net_gamma":net},
            {"strike_index":base+20,"net_gamma":-net*.75}]}
    return {"expiry":expiry.isoformat(),"usable":True,"rows":[
        {"strike":base,"net":net},{"strike":base+1,"net":-net*.75}]}


def mapping(symbol):
    etf=168.0 if symbol=="USO" else 368.0
    fut=101.0 if symbol=="USO" else 4070.0
    return {"etf_symbol":symbol,"etf_price":etf,
            "future_price":fut,"ratio":fut/etf,
            "future_tv_symbol":("NYMEX:CLZ2026" if symbol=="USO"
                                else "COMEX:GCZ2026"),
            "bar_ny":"2026-10-30T15:55:00-04:00",
            "source":"Synthetic synchronized bars"}


def profiles(symbol):
    base={"NDX":25500.0,"GLD":368.0,"USO":168.0}[symbol]
    d={}
    for i,(slot,t) in enumerate(TIMES):
        d[slot]={"0DTE":gamma_profile(symbol,base,DAY,(i+1)*2.5),
                 "Weekly":gamma_profile(symbol,base+10,FRIDAY,(i+1)*1.5),
                 "capture":capture(symbol,slot,t),
                 "close":base}
    return d


class TimePineTests(unittest.TestCase):
    def test_actual_utc_filename_converted_to_rome_cet(self):
        v=capture("NDX","0730","063100")
        self.assertEqual(v["rome"].strftime("%H:%M %Z"),"07:31 CET")
        self.assertEqual(v["slot"],"0730")
        with self.assertRaisesRegex(ValueError,"un'altra seduta"):
            parse_archived_capture(
                "NDX_20261103T063100Z_0730_aaaaaaaaaaaa.json.gz",
                "NDX",DAY)
        with self.assertRaisesRegex(ValueError,"non valido"):
            parse_archived_capture(
                "GLD_20261102T063100Z_0730_aaaaaaaaaaaa.json.gz",
                "NDX",DAY)

    def test_all_three_exports_contain_expected_real_profiles(self):
        for symbol in ("NDX","GLD","USO"):
            with self.subTest(symbol=symbol):
                p=profiles(symbol)
                mapping_or_basis=(140.0 if symbol=="NDX" else mapping(symbol))
                with patch("v2_pine_timed_exports.build_slot_profiles",
                           return_value=(p,{})):
                    code,errors,_=produce_timed_scripts(
                        symbol,DAY,{k:v["capture"] for k,v in p.items()},
                        p["0730"]["close"],3.0,mapping_or_basis)
                self.assertEqual(set(code),{"0730","1550","2030"},errors)
                self.assertIn("07:30 · 0DTE + Weekly",code["0730"])
                self.assertIn("0DTE 07:30 · Acq 07:31 CET",code["1550"])
                self.assertIn("0DTE 15:50 · Acq 15:51 CET",code["1550"])
                self.assertIn("Weekly 15:50 · Acq 15:51 CET",code["1550"])
                self.assertIn("0DTE 15:50 · Acq 15:51 CET",code["2030"])
                self.assertIn("0DTE 20:30 · Acq 20:51 CET",code["2030"])
                self.assertIn("Weekly 20:30 · Acq 20:51 CET",code["2030"])
                self.assertIn("showPrevious = input.bool(true",code["1550"])
                self.assertIn("var array<float> prevGamma =",code["2030"])
                self.assertIn("if barstate.islast and validTicker",code["2030"])
                self.assertIn("gammaPerCandle = input.float(",code["2030"])
                self.assertIn("0DTE 02/11 · Acq 07:31 CET",code["0730"])
                self.assertNotIn("showPrevious = input.bool",code["0730"])
                if symbol=="NDX":
                    self.assertIn("25640",code["1550"])  # 25500 NDX + 140 basis
                    self.assertIn("25640",code["2030"])
                else:
                    self.assertIn("mapETF(prevStrikesETF, ratioToDraw)",code["1550"])
                    self.assertIn("prevGamma",code["1550"])
                    self.assertIn("float lockedRatio =",code["0730"])

    def test_missing_previous_slot_fails_closed(self):
        all_p=profiles("NDX")
        only={"1550":all_p["1550"],"2030":all_p["2030"]}
        with patch("v2_pine_timed_exports.build_slot_profiles",
                   return_value=(only,{})):
            scripts,issues,_=produce_timed_scripts("NDX",DAY,{},25500.0,3.,140.)
        self.assertNotIn("1550",scripts)
        self.assertIn("2030",scripts)
        self.assertIn("Manca 0DTE precedente 07:30",issues["1550"])

    def test_reject_reversed_time_cross_day_expiry_mismatch(self):
        a=profiles("USO")
        with self.assertRaisesRegex(ValueError,"Fotografie non ordinate"):
            compare_capture_pair(a["1550"]["capture"],a["0730"]["capture"],
                                 "0730","1550")
        from v2_pine_comparison import make_pine_comparison_v2
        other=gamma_profile("USO",168.,FRIDAY,3.)
        with self.assertRaisesRegex(ValueError,"scadenze differenti"):
            make_pine_comparison_v2(
                "USO",other,a["1550"]["0DTE"],a["1550"]["Weekly"],
                mapping("USO"),DAY,a["0730"]["capture"],a["1550"]["capture"],
                "0730","1550",etf_previous_close=168.)

    def test_actual_profiles_not_modified_after_export(self):
        p=profiles("GLD")
        original=p["0730"]["0DTE"]["rows"][0]["net"]
        from v2_pine_comparison import make_pine_comparison_v2
        code=make_pine_comparison_v2(
            "GLD",p["0730"]["0DTE"],p["1550"]["0DTE"],
            p["1550"]["Weekly"],mapping("GLD"),DAY,
            p["0730"]["capture"],p["1550"]["capture"],
            "0730","1550",etf_previous_close=368.)
        self.assertEqual(original,p["0730"]["0DTE"]["rows"][0]["net"])
        self.assertIn("2.5",code)
        self.assertIn("5.0",code)


if __name__=="__main__":
    unittest.main()
