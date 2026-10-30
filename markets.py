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
    'NASDAQ': Market('NASDAQ','Nasdaq 100 (Cboe)','NDX / NDXP','NQ / MNQ','NQ − NDX',True,
                     'NDX index options: provisional transfer of the SPX 25+25 strike rule, pending cross-market validation.'),
    'GOLD': Market('GOLD','Gold · GLD (Cboe)','GLD ETF options · Cboe','GC / MGC (Pine indicativo)','Mappatura % ETF→future',True,'Cboe GLD originale: non CME GC.'),
    'WTI': Market('WTI','Petrolio · USO (Cboe)','USO ETF options · Cboe','CL / MCL (Pine indicativo)','Mappatura % ETF→future',True,'Cboe USO originale: non NYMEX CL.'),
}
