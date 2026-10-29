"""Market registry. Only Nasdaq is enabled until other feeds are validated."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Market:
    key: str
    label: str
    options: str
    futures: str
    basis: str
    enabled: bool
    info: str

MARKETS = {
    'NASDAQ': Market('NASDAQ','Nasdaq 100','NDX / NDXP','NQ / MNQ','NQ − NDX',True,
                     'NDX index options: provisional transfer of the SPX 25+25 strike rule, pending cross-market validation.'),
    'DAX': Market('DAX','DAX','ODAX','FDAX / FDXM','FDAX − DAX',False,'Eurex source and units to validate.'),
    'GOLD': Market('GOLD','Gold','Gold options on GC','GC / MGC','Not required for same-contract futures',False,'CME option contract, multiplier and access to Greeks to validate.'),
    'WTI': Market('WTI','WTI crude oil','WTI options on CL','CL / MCL','Not required for same-contract futures',False,'CME contract month matching and Greeks to validate.'),
    'EURUSD': Market('EURUSD','Euro / Dollaro','Euro FX options','6E / M6E','Not required for same-contract futures',False,'CME Euro FX option conventions and precision to validate.'),
    'ZB': Market('ZB','Treasury 30Y','Treasury bond options','ZB','Not required for same-contract futures',False,'CME option conventions and fractional-price ticks to validate.'),
}
