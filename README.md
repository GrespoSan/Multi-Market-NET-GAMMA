# Multi-Market NET GAMMA — prototype 0.1

**Independent project, does not modify the Serafini SPX code, GitHub repository, or Supabase bucket.**

## Current scope

- Six-instrument selector: Nasdaq / DAX / Gold / WTI / EURUSD / ZB.
- **Nasdaq NDX/NQ remains enabled.** Gold GLD (ETF) has a separate **Cboe original-file NET GAMMA** mode with no Alpaca dependency; DAX, WTI, EURUSD and ZB remain disabled. GLD levels are NOT Gold future GC levels.
- Cboe `_NDX.json` fetch *on demand* or imported `.json` / `.json.gz` original file.
- NDX and NDXP contracts parsed using expiry, put/call and strike from original OCC code.
- `(OI+Volume)*Gamma` Call minus Put unchanged; all real NDX strikes in a **user-adjustable ±% band** centered on the previous NDX close (default ±3%; same band for 0DTE and Weekly).
- 0DTE and next Friday Weekly retain only their actual expirations; their graphs share the **same y-price window and x-gamma scale**. No fixed 25+25 cap, interpolation or synthetic strikes.
- NQ-NDX basis from **synchronized previous-session 15m Yahoo bars**, with adjustable manual input. Yahoo NQ=F may not match the TradingView/broker futures contract; validate before using.
- Two gamma plots; optional side-by-side **NET GAMMA left + NQ=F 5-minute candlesticks right**, with synchronized NQ price axis. The 5m fetch runs only when the comparison view is activated.
- Pine v6 export for 0DTE, Weekly and combined, with manual gamma/bar scale. Exports include all selected strikes until TradingView's 500-line limit, and block explicitly if it would exceed 480 gamma lines (room for news).
- NQ−NDX basis is calculated automatically after loading a NDX snapshot using previous-session synchronized Yahoo 15m closes. It stays editable and can be recalculated manually. Pine downloads do not recalculate it.
- The three Pine exports automatically include USA macro news vertical lines, only for date/time events available from Finance Calendar. The lines can be turned off in the Pine settings.
- Pine input controls match the SPX export (manual Gamma/bar, independent column distances, colors, titles, macro lines), but **the NDX numeric Gamma/bar default is chosen from the actual exported NDX profiles**. A fixed SPX default of 1 Gamma/bar is usually too large for NDX and collapses the bars. The value is suggested only at export time and remains manually adjustable in TradingView; no Gamma values are normalized or modified. NDX drawing is guarded to NQ/MNQ futures; SPX drawing to ES/MES futures. Ticker mismatch hides all overlay drawings.
- Download buttons do not cause full Streamlit reruns (`on_click="ignore"`).

## GLD mode (Cboe original-file only)

- Select **Gold · GLD (Cboe)** in the Multi-Market Streamlit selector.
- Open the original [Cboe GLD.json](https://cdn.cboe.com/api/global/delayed_quotes/options/GLD.json) manually and save its original bytes as GLD.json. Import that JSON (or its .json.gz compression) using the file uploader in the Gold module.
- No Alpaca credentials, requests, Greek approximation, weekly IV proxy or Open Interest-only fallback are used; the prior Alpaca GLD code and tests have been deleted.
- Cboe GLD input is strictly validated: GLD OCC contract root only, actual expiration, true Cboe Gamma, OI and Volume, no synthetic strikes/expiry, and no missing inputs silently substituted with zero.
- The formula is **NET = [(OI+Volume)×Gamma] Call − [(OI+Volume)×Gamma] Put**, directly from the imported GLD option chain. It is not cash gamma exposure, inferred dealer inventory, or GC futures gamma.
- The user selects the **primary expiration**; it is labeled 0DTE only when it matches today's date in **America/New_York**. Weekly is the next real Friday expiration present in the chain, or marked unavailable. Both plots share the same user-adjustable ±% strike window (from previous close) and x-axis scale.
- Display original file timestamp **without inferring its timezone**, local import time separately, coverage, missing fields and a CSV export for each usable expiry. The import timestamp does not certify the age of the chain.
- Cboe's delayed-quote web page explicitly restricts programmatic extraction. Consequently, this module does **not** automatically fetch GLD.json, create cron/GitHub workflows, or copy SPX's existing Cboe downloader. Automated collection requires a permissible/licensed source. The existing Serafini SPX and Nasdaq NDX modules are unchanged.
- No historical replay, Pine GLD overlay, GLD-to-GC conversion, gamma flip or scheduled snapshots are implemented in GLD mode.

## Run

```shell
pip install -r requirements.txt
streamlit run app.py
```

Or deploy this folder as a new independent Streamlit application; main file `app.py`.

## Important technical limitations

1. GLD Cboe original-file validation is unit-tested with fixtures, but its live JSON field layout and its 0DTE Gamma completeness must still be confirmed with a fresh real file in Streamlit. NDX live feed limitations remain separately documented.
2. The formula and adjustable percentage strike band are a cross-market study choice, **not independently validated for Nasdaq by Serafini**. We do not apply the 60% 0DTE / 23% Weekly SPX percentages to Nasdaq.
3. No automated schedule, archive, replay, Supabase link or new GitHub repo is created at this stage; GLD data is manually imported.
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
