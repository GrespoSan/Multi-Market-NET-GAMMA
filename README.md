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
- Cboe places restrictions on automated extraction of delayed quotes. A single **user-triggered** request now follows the same interaction pattern as Nasdaq's Cboe button; nessun download automatico dal sito delayed_quotes Cboe è introdotto. Una pipeline separata attende un feed autorizzato. Use of the data remains subject to Cboe terms. The existing Serafini SPX and Nasdaq NDX modules are unchanged.
- The app exports **Pine Script v6 for GC/MGC futures** (main/0DTE, Weekly, or both), using a **5-minute synchronized, frozen ETF/futures price ratio**, or an explicitly declared manual fallback. This is **not native GC gamma**. The exporter never modifies the original NET GAMMA. No historical replay, Gamma Flip or scheduled snapshots are implemented in GLD mode.

## Petrolio USO (Cboe ETF options)

- Select **Petrolio · USO (Cboe)** in the Multi-Market selector, then click **Aggiorna fotografia USO da Cboe** for the original USO option-chain snapshot (one user-triggered request, no cron). If blocked, use the original JSON upload in the fallback expander.
- Direct source: https://cdn.cboe.com/api/global/delayed_quotes/options/USO.json . The original JSON or .json.gz is verified to be USO; invalid files and other instrument symbols are rejected.
- Original Gamma, Open Interest and Volume are used without estimation: **NET = [(OI+Volume) × Gamma] Call − [(OI+Volume) × Gamma] Put** at every real strike inside the user-adjustable common percentage band around USO previous close.
- **0DTE** is labeled only for a contract actually expiring on the current New York date; **Weekly** is the next Friday actually found in the Cboe option chain (or shown as unavailable). When Gamma is absent or insufficient, the profile is not published. Charts share price and gamma axes. Validated CSV exports remain in USO units.
- USO is an oil-futures-linked exchange-traded product, *not* the WTI CL/MCL future and *not* the NYMEX option chain; do **not** transfer or rescale USO strikes into CL levels.
- **OVX context:** https://www.cboe.com/us/indices/dashboard/ovx/ . OVX is the Cboe 30-day implied-volatility index derived from USO options; currently linked for context only, not used in the NET GAMMA arithmetic. No OVX value is guessed.
- Identical source access limits as GLD: Cboe restrictions remain relevant, the automatic/unattended 07:30 and 15:50 captures are **not** implemented for USO. No Serafini SPX, NDX or GLD code/market logic is modified by this addition.
- USO engine and original-file importer are unit-tested with illustrative **synthetic fixtures**, not a certification that the live server currently accepts Streamlit requests or that all 0DTE options supply usable Gamma. Run a fresh USO capture in the deployed app to validate.
- The app exports **Pine Script v6 for CL/MCL futures** (main/0DTE, Weekly, or both), using a **5-minute synchronized, frozen ETF/futures price ratio**, or an explicitly declared manual fallback, **not native CL gamma**.

## Standard grafico Pine · Serafini SPX

The **Serafini SPX NET GAMMA** Pine exporter is the reference visual layout for
**all three markets**. The Multi-Market generators share `pine_spx_visual.py`
for the same manual Gamma/bar scale, dotted vertical baselines, green/red horizontal
Gamma bars of width 5, adjustable 0DTE/Weekly column offsets (default 60/160),
titles, and last-bar/TradingView line-limit guard. The SPX application itself is
unchanged; its market-specific 25+25 selection rule is NOT automatically applied
to the other markets.

No ratio status/disclaimer label is drawn over candles in Gold or Oil anymore.
The frozen ratio, timestamp, ETF and futures prices, and contract remain documented
in the Pine **source comments** and in the Streamlit export panel. The only
conditional warning drawn on the chart is the shared SPX-style safety warning if
the user's *manual* Gamma/bar scale would exceed TradingView's drawing limit.
Any change to the common visual style should be made in `pine_spx_visual.py`,
then validated for **Nasdaq NQ/MNQ, Gold GC/MGC, Petrolio CL/MCL** together.

## Pine v6: ETF-option Gamma over corresponding futures (synchronized frozen ratio)

- Nasdaq NDX → **NQ/MNQ** retains the original independent exporter and NQ−NDX basis.
- GLD → **GC/MGC**, USO → **CL/MCL**: the original ETF (Call [(OI+Volume)×Gamma] − Put [(OI+Volume)×Gamma]) is unchanged. These are **illustrative price projections** of ETF strikes, NOT native futures option Gamma.
- The app reads the Cboe snapshot, then **once per original file hash and chosen month-specific futures contract** attempts to retrieve two **5-minute completed bars with exactly the same UTC timestamp** (no nearest-neighbor matching): Yahoo GLD and the chosen `GCZ26.CMX` (or `GCG27.CMX`), or USO and `CLZ26.NYM` (or `CLF27.NYM`). Only regular ETF trading 09:30–16:00 New York bars are considered. Delayed/stale or nonexistent pairs block the automatic ratio. These are Yahoo quotes and may differ from exchange/broker realtime data.
- The **locked ratio** is `future_close_5m / ETF_close_5m`. The two prices, precise matching bar time in New York, source, contract, ratio and original Cboe snapshot hash are retained in Streamlit session. The mapped future price is `ETF_strike × locked_ratio`. On each new Cboe file or different futures contract the old ratio becomes invalid; no previous/unsynchronized price is substituted.
- If Yahoo does not provide a synchronized pair, exports are **blocked** pending the explicit reattempt or **manual fallback**. The manual fallback requires two same-time prices plus the observed New York clock time, and is labeled **user-declared, not independently verified**.
- Every Pine embeds the frozen ratio as a numeric literal; its default input is **Bloccato** and stays unchanged through future sessions. Optional **Dinamico** refreshes only when TradingView obtains completed 5-minute ETF/future bars with **equal timestamps**, carrying forward the last valid ratio when the ETF market is closed. On chart timeframes above 5 minutes the dynamic mode falls back to the frozen ratio. Turning on the dynamic mode can move *all* drawn levels; it is not appropriate if the user wants static levels from a particular options snapshot.
- Each script restricts display to relevant futures roots (GC/MGC or CL/MCL) and identifies the **chosen dated futures contract**. On continuous symbols GC1!/CL1!, double-check the effective futures month and roll dates. 0DTE, Weekly and combined exports follow the Cboe chain's **real** expirations; there is no expiry synthesis.
- The Cboe snapshot's original timestamp has **no documented time zone** in the raw file. We can sync ETF and futures *to each other* by the exact 5-minute bar timestamp, but **cannot claim that this pair has the same exact instant as the Cboe chain**, unless the source timezone is independently verified. The app explicitly shows both observations.
- Data acquisition remains manual-on-demand and subject to Cboe/Yahoo source terms. Pine compilation and live ratio behavior require final verification on TradingView. Do not label these projections genuine CME/NYMEX option support/resistance.

## Nuovo cruscotto e rilevamenti programmati

### Restyling grafico

- `gamma_chart_style.py` definisce l'unico tema scuro Plotly di **Nasdaq, Gold e Petrolio**: scale Gamma e prezzo identiche tra 0DTE e Weekly, barre positive verdi / negative rosse, linea del close precedente gialla, griglia discreta, hover con Gamma / OI / Volume quando disponibili.
- L'app indica il livello strike del **Gamma positivo** e **Gamma negativo** più marcato per ciascuna scadenza. Sono massimi e minimi della formula esistente, NON gamma flip o dealer walls.
- `pine_spx_visual.py` resta il modello comune per i Pine: questa modifica riguarda il grafico web, NON ricalcola Gamma o sposta i livelli.

### Tre orari Europe/Rome, lunedì–venerdì

Workflow GitHub Actions: `.github/workflows/multi-market-snapshots.yml`.

| Rilevamento nominale (Roma) | Fuso | Simboli |
|---|---|---|
| 07:30 | Europe/Rome con DST automatico | NDX, GLD, USO |
| 15:50 | Europe/Rome con DST automatico | NDX, GLD, USO |
| 20:30 | Europe/Rome con DST automatico | NDX, GLD, USO |

Il runner verifica finestra effettiva **0–12 minuti** (esecuzioni GitHub possono essere ritardate), non rietichetta retroattivamente acquisizioni fuori finestra, e non esegue acquisizioni ufficiali nei weekend. Ogni singolo mercato riceve un esito `SCARICATO`, `NON_CONFIGURATO` o `ERRORE`; la fotografia originale con timestamp della fonte non viene mai camuffata come quella dell'orario richiesto. Download invariato/duplicato significa dati Cboe/provider identici, non dati nuovi.

**Vincolo contrattuale importante:** il sito di opzioni ritardate Cboe proibisce espressamente l'estrazione automatizzata. Il workflow NON usa `cdn.cboe.com/.../delayed_quotes/...`, rifiuta URL o redirect a questo endpoint e non tenta aggiramenti. Il download diretto da Streamlit continua a richiedere un clic manuale. Per attivare davvero i tre orari serve un **feed autorizzato per acquisizione automatica** che fornisca JSON compatibile con le catene NDX, GLD e USO e i campi Gamma, Open Interest e Volume. Le tre URL non sono inventate.

#### Configurazione necessaria una sola volta

1. In **GitHub → GrespoSan/Multi-Market-NET-GAMMA → Settings → Secrets and variables → Actions**, aggiungere secrets server-side `MM_FEED_NDX_URL`, `MM_FEED_GLD_URL`, `MM_FEED_USO_URL` (endpoint API https autorizzati; non delayed_quotes) e facoltativamente `MM_FEED_TOKEN` (autenticazione Bearer).
2. Creare un bucket **privato**, non pubblico, `multi-market-snapshots` nel progetto Supabase scelto. Non usare `spx-snapshots` e non modificare l'archivio SPX. Impostare nel nuovo repository GitHub i secret `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY` relativi a quel progetto. NON inserire le credenziali nel codice o in chat.
3. Quando gli endpoint sono autorizzati e il bucket privato è pronto, impostare la variabile di repository GitHub Actions `MM_AUTHORIZED_FEED_CONFIRMED=true`. Senza quella variabile, le esecuzioni **programmate restano deliberatamente disattivate**; la workflow manuale permette solo diagnosi senza estrazioni non autorizzate.
4. Per selezionare le fotografie archiviate direttamente nella pagina Streamlit, inserire nella sua configurazione privata `secrets.toml` **gli stessi** `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY`, più `MM_SUPABASE_BUCKET="multi-market-snapshots"` e **`MM_ARCHIVE_ACCESS_CODE`** (una password robusta, solo nei secret). L'archivio resta disattivato senza questo codice; la password viene confrontata lato server. Limitare inoltre l'accesso a Streamlit agli utenti autorizzati. La service-role key è un segreto server-side potente e non deve mai apparire nel repository, negli script Pine o nei log.
5. Ogni run scrive **soltanto log e stato** negli artifact GitHub Actions (30 giorni). I file dati delle opzioni vengono salvati unicamente nel bucket privato con path `snapshots/{NDX|GLD|USO}/{YYYY-Www}/`. I log privati sono in `logs/{symbol}/{YYYY-Www}/`. I tre mercati restano indipendenti. Gli archivi si leggono con l'expander nell'app; i rilevamenti assenti sono esplicitamente non disponibili.
6. Test iniziale: in **Actions → Multi-Market fotografie → Run workflow**, controllare i log. Non confondere un workflow eseguito con uno snapshot realmente salvato; verificare `SCARICATO` per ciascun mercato.

L'archivio e i rilevamenti programmati non sono dichiarati attivi finché non sono configurati i feed autorizzati e le credenziali di storage. La versione SPX continua a usare il proprio repository e bucket separati.

## Run

```shell
pip install -r requirements.txt
streamlit run app.py
```

Or deploy this folder as a new independent Streamlit application; main file `app.py`.

## Important technical limitations

1. GLD Cboe parsing and one-click fetch are unit-tested with fixtures, but server access, the live JSON layout and its 0DTE Gamma completeness must still be confirmed in Streamlit with a fresh real snapshot. NDX live feed limitations remain separately documented.
2. The formula and adjustable percentage strike band are a cross-market study choice, **not independently validated for Nasdaq by Serafini**. We do not apply the 60% 0DTE / 23% Weekly SPX percentages to Nasdaq.
3. La programmazione per tre orari è **predisposta ma non attiva senza fonte autorizzata**; l'archivio privato Supabase e il selettore Streamlit richiedono secret configurati. Il download Cboe diretto rimane manuale.
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
