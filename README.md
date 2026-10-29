# Multi-Market NET GAMMA — prototype 0.1

**Independent project, does not modify the Serafini SPX code, GitHub repository, or Supabase bucket.**

## Current scope

- Three-market selector: **Nasdaq NDX/NQ**, **Gold GLD (ETF)** and **Petrolio USO (ETF)**.
- Pine exports now available per futures chart: **Nasdaq NQ/MNQ** (existing NDX−NQ basis), **Gold GC/MGC** (GLD option data mapped by percentage), and **Petrolio CL/MCL** (USO option data mapped by percentage). Original Cboe Gamma is never changed; ETF levels on futures are illustrative, not true native options-Gamma levels.
- **Nasdaq NDX/NQ remains enabled.** Gold GLD (ETF) and Petrolio USO (ETF) have separate **Cboe on-demand NET GAMMA** modes with no Alpaca dependency. Neither GLD nor USO strikes are native futures-option strikes (GC / CL).
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
- Click **Aggiorna fotografia GLD da Cboe** to request and validate the original GLD.json directly inside Streamlit (one user action; no polling). If the hosting server is blocked by Cboe, expand **Importazione manuale del JSON originale** and import GLD.json (or original .json.gz), available at [Cboe GLD.json](https://cdn.cboe.com/api/global/delayed_quotes/options/GLD.json).
- No Alpaca credentials, requests, Greek approximation, weekly IV proxy or Open Interest-only fallback are used; the prior Alpaca GLD code and tests have been deleted.
- Cboe GLD input is strictly validated: GLD OCC contract root only, actual expiration, true Cboe Gamma, OI and Volume, no synthetic strikes/expiry, and no missing inputs silently substituted with zero.
- The formula is **NET = [(OI+Volume)×Gamma] Call − [(OI+Volume)×Gamma] Put**, directly from the imported GLD option chain. It is not cash gamma exposure, inferred dealer inventory, or GC futures gamma.
- The user selects the **primary expiration**; it is labeled 0DTE only when it matches today's date in **America/New_York**. Weekly is the next real Friday expiration present in the chain, or marked unavailable. Both plots share the same user-adjustable ±% strike window (from previous close) and x-axis scale.
- Display original file timestamp **without inferring its timezone**, local import time separately, coverage, missing fields and a CSV export for each usable expiry. The import timestamp does not certify the age of the chain.
- Cboe places restrictions on automated extraction of delayed quotes. A single **user-triggered** request now follows the same interaction pattern as Nasdaq's Cboe button; no unattended/scheduled job, scraping loop, bypass, or Cboe API authentication is introduced. Use of the data remains subject to Cboe terms. The existing Serafini SPX and Nasdaq NDX modules are unchanged.
- The app now exports **Pine Script v6 for GC/MGC futures** (main/0DTE, Weekly, or both), with a clearly labeled **percentage price mapping** of Cboe GLD ETF strikes. This is **not native GC gamma**. The exporter never modifies the original NET GAMMA. No historical replay, Gamma Flip or scheduled snapshots are implemented in GLD mode.

## Petrolio USO (Cboe ETF options)

- Select **Petrolio · USO (Cboe)** in the Multi-Market selector, then click **Aggiorna fotografia USO da Cboe** for the original USO option-chain snapshot (one user-triggered request, no cron). If blocked, use the original JSON upload in the fallback expander.
- Direct source: https://cdn.cboe.com/api/global/delayed_quotes/options/USO.json . The original JSON or .json.gz is verified to be USO; invalid files and other instrument symbols are rejected.
- Original Gamma, Open Interest and Volume are used without estimation: **NET = [(OI+Volume) × Gamma] Call − [(OI+Volume) × Gamma] Put** at every real strike inside the user-adjustable common percentage band around USO previous close.
- **0DTE** is labeled only for a contract actually expiring on the current New York date; **Weekly** is the next Friday actually found in the Cboe option chain (or shown as unavailable). When Gamma is absent or insufficient, the profile is not published. Charts share price and gamma axes. Validated CSV exports remain in USO units.
- USO is an oil-futures-linked exchange-traded product, *not* the WTI CL/MCL future and *not* the NYMEX option chain; do **not** transfer or rescale USO strikes into CL levels.
- **OVX context:** https://www.cboe.com/us/indices/dashboard/ovx/ . OVX is the Cboe 30-day implied-volatility index derived from USO options; currently linked for context only, not used in the NET GAMMA arithmetic. No OVX value is guessed.
- Identical source access limits as GLD: Cboe restrictions remain relevant, the automatic/unattended 07:30 and 15:50 captures are **not** implemented for USO. No Serafini SPX, NDX or GLD code/market logic is modified by this addition.
- USO engine and original-file importer are unit-tested with illustrative **synthetic fixtures**, not a certification that the live server currently accepts Streamlit requests or that all 0DTE options supply usable Gamma. Run a fresh USO capture in the deployed app to validate.
- The app now exports **Pine Script v6 for CL/MCL futures** (main/0DTE, Weekly, or both), using a labeled percentage mapping of USO ETF strike prices, **not native CL gamma**.

## ETF Gamma display on corresponding futures (Pine v6)

For both Gold and Petrolio, after a Cboe profile is usable, choose one of three downloadable scripts: principal/0DTE only, Weekly only, or principal/0DTE + Weekly. The code is also visible for copy/paste. Each script shows on **its own futures root only**:

- GLD Cboe options → COMEX **GC/MGC** TradingView futures.
- USO Cboe options → NYMEX **CL/MCL** TradingView futures.
- Nasdaq NDX → **NQ/MNQ** continues using its original independent Pine exporter.

**This is not a direct strike translation.** By default TradingView supplies the previous completed Daily futures close and the Pine plots `future_reference × (ETF_option_strike / ETF_previous_close)`. A manually supplied future reference (from the same reference session as the ETF close) locks the plotted levels to that reference. With automatic Daily reference the mapping can shift next session, and futures/ETF trading sessions are not perfectly synchronized.

Thus the resulting levels are **percentage-projected positions of ETF Gamma, not CME/NYMEX options levels or validated support/resistance on the future**. All profiles are labeled accordingly. No fabricated CME/NYMEX contracts, no conversion of Gamma weights, and no supposed equality of USO and CL prices. Inspect the mapping before trading. The Pine scripts are syntactically generated and regression-tested, but must still be checked in the TradingView Pine editor.

## Run

```shell
pip install -r requirements.txt
streamlit run app.py
```

Or deploy this folder as a new independent Streamlit application; main file `app.py`.

## Important technical limitations

1. GLD Cboe parsing and one-click fetch are unit-tested with fixtures, but server access, the live JSON layout and its 0DTE Gamma completeness must still be confirmed in Streamlit with a fresh real snapshot. NDX live feed limitations remain separately documented.
2. The formula and adjustable percentage strike band are a cross-market study choice, **not independently validated for Nasdaq by Serafini**. We do not apply the 60% 0DTE / 23% Weekly SPX percentages to Nasdaq.
3. No automated schedule, archive, replay, Supabase link or new GitHub repo is created at this stage; GLD refresh is user-triggered, with optional manual import fallback.
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
