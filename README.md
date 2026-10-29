# Multi-Market NET GAMMA — prototype 0.1

**Independent project, does not modify the Serafini SPX code, GitHub repository, or Supabase bucket.**

## Current scope

- Six-instrument selector: Nasdaq / DAX / Gold / WTI / EURUSD / ZB.
- **Nasdaq NDX/NQ remains enabled.** Gold has a separate experimental **GLD ETF** mode sourced from Alpaca; DAX, WTI, EURUSD and ZB remain disabled. There is no CME GC NET GAMMA in GLD mode.
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

## GLD mode (Alpaca API, experimental)

- Choose **Gold · ETF GLD (sperimentale)**. The button fetches GLD ETF option contracts (Open Interest, dated) and indicative-feed snapshots (Gamma, daily volume) from Alpaca, read-only. **The connected ChatGPT Alpaca plugin does not automatically authenticate a Streamlit app.**
- Set the following keys in Streamlit Community Cloud app **Settings → Secrets** or local environment (never commit values):

```toml
APCA_API_KEY_ID = "your-paper-api-key-id"
APCA_API_SECRET_KEY = "your-paper-api-secret"
```

- The option source is **GLD (equity ETF), not CME Gold future GC**. No strike or level is translated to GC. The experiment uses the same `(OI+Volume)*Gamma` algebra but is neither monetary GEX nor validated dealer exposure.
- GLD 0DTE follows **New York** calendar day; Weekly uses **next Friday**, with no synthetic expiry. If the actual contracts are missing, no profile is drawn.
- Profiles need matched Call and Put at each real strike, nonmissing Gamma, OI and daily volume, a minimum 70% contract-data coverage, and at least two complete strikes. Missing values are never filled with zero. Source date of OI and completeness are always displayed.
- The indicative options feed contains delayed/modified trade/quote data. Data freshness, trading hours and availability depend on the Alpaca account; no claim of live OPRA pricing. No automatic scheduler yet; press **Aggiorna fotografia** to update.
- **29 October 2026 live verification:** Alpaca's `indicative` feed returned no Gamma for sampled same-day GLD and SPY 0DTE contracts, while the next-day GLD option feed supplied Greeks. The account's requested `opra` feed responded `OPRA agreement is not signed`. Do not silently use OI or volume as Gamma.
- If GLD 0DTE lacks Gamma, the app can now show an explicitly separate **Open Interest ONLY** graphic, if the real Call/Put OI has sufficient coverage. This is NOT GEX or NET GAMMA; OI can be older than the observation date.
- **Experimental 0DTE Gamma estimation** (file `gld_gamma_estimate.py`): because Alpaca explicitly does not provide Greeks for same-day expiring contracts, the app can calculate an *approximate*, Black–Scholes gamma using the ETF GLD IEX bid/ask midpoint, expiration at 16:15 New York (13:15 manual early-close option), and remaining intraday clock time. It prefers the Alpaca 0DTE contract IV if available, otherwise attempts to solve IV from that option's indicative bid/ask midpoint; if enabled, it can fall back to **the next-Friday option IV at exactly the same GLD strike and call/put side**. Each row records its IV provenance.
- Model assumptions: GLD American-style option modeled with **European Black–Scholes approximation**, zero dividend yield, manually adjustable annual rate (default **3.5% is an assumption, not a data feed**), an indicative/modified options feed, an IEX-only stock quote and OI that may be lagged. This is **not direct/observed GLD Gamma**, not GC future options, not dollar GEX, and not dealer inventory. Proxy IV comes from a *different expiry* and may not reflect 0DTE volatility.
- Data safeguards: trading window 09:30–16:15 New York or the manually selected early 13:15 close; stop estimates within 15 minutes of expiry; use only recent (3-minute alignment) option/underlying quotes with a GLD spot quote captured within 5 minutes of acquisition; reject crossed, illiquid, too-wide or unpriced options; reject missing OI, volume, incomplete sides, invalid multipliers, and stale daily bars. No rows are published unless at least 3 real strike pairs are complete and contract coverage is 70% or more. Snapshots older than 10 minutes must be refreshed. If the model fails, retain the separate OI-only fallback.
- The GLD controls are **manual** and limited to the experimental module. Nasdaq NDX/NQ logic and Serafini SPX are untouched. The estimated Gamma displays IV provenance, missing coverage and a CSV tagged `STIMATO`. No automatic 07:30/15:50 schedule has been enabled.
- Source of Alpaca 0DTE limitation: https://docs.alpaca.markets/us/docs/market-data-faq ; GLD options regular trading close 16:15 ET: https://www.nasdaqtrader.com/Trader.aspx?id=optionshours .
- GLD CSV export is available. GC NET GAMMA, Pine overlay, historical replay, gamma flip and scheduled snapshots are **not** implemented for GLD.

## Run

```shell
pip install -r requirements.txt
streamlit run app.py
```

Or deploy this folder as a new independent Streamlit application; main file `app.py`.

## Important technical limitations

1. Cboe feed URL is publicly documented but could **not be queried live from the development sandbox**. Actual field formats / endpoint reachability must be verified with a real NDX JSON. Contract parser is intentionally strict and the app rejects malformed/partial snapshots.
2. The formula and adjustable percentage strike band are a cross-market study choice, **not independently validated for Nasdaq by Serafini**. We do not apply the 60% 0DTE / 23% Weekly SPX percentages to Nasdaq.
3. No automated schedule, archive, replay, Supabase link or new GitHub repo is created at this stage; GLD refresh is manually triggered.
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
