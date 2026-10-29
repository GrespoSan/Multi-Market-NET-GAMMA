"""Market registry: Nasdaq NDX, Gold GLD and Oil USO enabled via Cboe."""
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
    'GOLD': Market('GOLD','Gold · GLD (Cboe)','GLD ETF options · Cboe','GLD ETF (non GC)','Livelli esclusivamente ETF GLD',True,'Cboe GLD originale: NON CME GC.'),
    'WTI': Market('WTI','Petrolio · USO (Cboe)','USO ETF options · Cboe','USO ETF (non CL)','Livelli esclusivamente ETF USO',True,'Cboe USO originale: NON opzioni sul future WTI CL/MCL.'),
    'EURUSD': Market('EURUSD','Euro / Dollaro','Euro FX options','6E / M6E','Not required for same-contract futures',False,'CME Euro FX option conventions and precision to validate.'),
    'ZB': Market('ZB','Treasury 30Y','Treasury bond options','ZB','Not required for same-contract futures',False,'CME option conventions and fractional-price ticks to validate.'),
}
