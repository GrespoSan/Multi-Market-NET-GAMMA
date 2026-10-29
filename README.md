# Multi-Market NET GAMMA — prototype 0.1

**Independent project, does not modify the Serafini SPX code, GitHub repository, or Supabase bucket.**

## Current scope

- Six-instrument selector: Nasdaq / DAX / Gold / WTI / EURUSD / ZB.
- **Only Nasdaq NDX/NQ is enabled.** The other five explicitly display status 'not operational' without fabricated levels.
- Cboe `_NDX.json` fetch *on demand* or imported `.json` / `.json.gz` original file.
- NDX and NDXP contracts parsed using expiry, put/call and strike from original OCC code.
- Experimental Serafini-SPX-derived `(OI+Volume)*Gamma`, Call minus Put, 25 strikes below and 25 above previous NDX close.
- 0DTE and next Friday weekly only if the exact expiration and complete 25+25 strike data exist.
- NQ-NDX basis from **synchronized previous-session 15m Yahoo bars**, with adjustable manual input. Yahoo NQ=F may not match the TradingView/broker futures contract; validate before using.
- Two gamma plots; Pine v6 export for 0DTE, Weekly and combined, with manual gamma/bar scale.
- NQ−NDX basis is calculated automatically after loading a NDX snapshot using previous-session synchronized Yahoo 15m closes. It stays editable and can be recalculated manually. Pine downloads do not recalculate it.
- The three Pine exports automatically include USA macro news vertical lines, only for date/time events available from Finance Calendar. The lines can be turned off in the Pine settings.
- Download buttons do not cause full Streamlit reruns (`on_click="ignore"`).

## Run

```shell
pip install -r requirements.txt
streamlit run app.py
```

Or deploy this folder as a new independent Streamlit application; main file `app.py`.

## Important technical limitations

1. Cboe feed URL is publicly documented but could **not be queried live from the development sandbox**. Actual field formats / endpoint reachability must be verified with a real NDX JSON. Contract parser is intentionally strict and the app rejects malformed/partial snapshots.
2. Calculations and strike selection are exploratory transfers of an SPX-specific teaching method, **not yet validated by Serafini for Nasdaq**. We do not apply the 60% 0DTE / 23% Weekly SPX percentages to Nasdaq.
3. No automated schedule, archive, replay, Supabase link or new GitHub repo is created at this stage.
4. The Cboe timestamp is shown as supplied; no timezone is inferred. Importing a file does not claim to know the original download time.
5. No cross-instrument multiplier normalization or claim about monetary GEX.
6. This prototype must be tested on live NDX and with a Pine v6 editor before operational trading.

## Source validation

Documented endpoint: `https://cdn.cboe.com/api/global/delayed_quotes/options/_NDX.json`
NDX quote page: https://www.cboe.com/delayed_quotes/NDX/quote_table/

## Testing

```shell
python -m unittest discover -s tests -v
```
