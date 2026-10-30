# Multi-Market NET GAMMA V2 · clonazione architettura Serafini SPX

**Stato:** V2 in ramo di sviluppo `v2-spx`, non sostituisce la Serafini SPX esistente.
La V1 su `main` resta sospesa. L'UI principale della V2 segue la struttura
di `Serafini-SPX-Dashboard/app.py`, SENZA GEX EDGE, Replay e confronto,
Report giornaliero AI.

## Architettura

- `app.py` — shell SPX con password distinte amministratore/lettore,
  Analisi del contesto e Analisi NET GAMMA.
- `v2_market_engine.py` — motore Multi-Market preesistente: NDX/NDXP,
  differenziale NQ−NDX, grafici NET GAMMA e Pine NQ/MNQ.
- `gld_cboe_view.py` / `uso_cboe_view.py` — catene GLD/USO originali,
  0DTE/Weekly, conversione con rapporto ETF/future congelato e Pine GC/MGC,
  CL/MCL. I Gamma sono sempre quelli originali degli ETF, non delle opzioni
  native sui futures.
- `v2_storage_off.py` — zero chiamate Supabase; importazione manuale degli
  artifact cifrati V2, accessibile all'amministratore soltanto.
- `v2_cron.py` — acquisizione da API **autorizzate per uso automatico**,
  validazione dati, archiviazione con crittografia Fernet in GitHub Actions.
  Nessun JSON opzioni non cifrato viene scritto sul disco del job.
- `gamma_chart_style.py` e `pine_spx_visual.py` — visualizzazione stile SPX.

Il contesto News/VIX/Trend Daily specifico di SPX non è stato attribuito
arbitrariamente ai mercati NDX/GLD/USO. La relativa sezione è presente
ma richiede dati e regole specifici per ogni mercato.

## Sospensione V1 e Supabase

Il file `app.py` sul ramo `main` mostra soltanto la manutenzione, senza
inizializzare Supabase, chiamare un downloader o importare motori di mercato.
Il workflow V1 di download è stato eliminato da `main`; il suo vecchio
workflow ereditato su `v2-spx` è stato neutralizzato (job sempre disabilitato).

**IMPORTANTE:** le vecchie chiavi eventualmente ancora presenti
in Streamlit/GitHub non possono essere cancellate tramite questa integrazione.
Rimuovere nella vecchia app i Secrets `SUPABASE_URL`,
`SUPABASE_SERVICE_ROLE_KEY` e altri riferimenti Supabase SOLO se non sono
condivisi con altri sistemi. Non cancellare né ruotare le chiavi del progetto
Serafini SPX: ciò potrebbe interrompere la SPX.

## Avvio della V2 su Streamlit

1. Crea un'app Streamlit **separata**, scegli repository
   `GrespoSan/Multi-Market-NET-GAMMA`, **branch `v2-spx`**, file `app.py`.
   La V1 pubblicata su `main` rimane sospesa.
2. Nella nuova app, in **Secrets**, imposta due password DISTINTE:
   `V2_ADMIN_PASSWORD` e `V2_FRIENDS_PASSWORD`. Non copiarle in chat,
   GitHub o nei file versionati; non servono Secrets Supabase.
3. Per ora le tre catene possono essere acquisite col pulsante manuale,
   come nella V1, o caricando il JSON originale Cboe.
4. Per importare un file cifrato, l'app deve avere anche
   `V2_ARCHIVE_FERNET_KEY`, identica a quella del workflow GitHub.
   Nell'espander **RILEVAMENTI CBOE** si può caricare manualmente
   il file `.json.gz.enc` scaricato dagli artifact GitHub Actions.

## Tre cronjob GitHub Actions

Workflow **sul ramo predefinito `main`**:
`.github/workflows/v2-spx-snapshots.yml`; effettua checkout del ramo
`v2-spx` prima di eseguire lo script. Questo permette di mantenere la V1
sospesa senza dover pubblicare o promuovere il codice V2.

Cron lunedì-venerdì, fuso `Europe/Rome` (DST automatico):
- `07:30`
- `15:50`
- `20:30`

La finestra di avvio valida è compresa tra l'orario nominale e 12 minuti
dopo. Le GitHub Actions possono partire in ritardo: i job fuori finestra
registrano uno SKIP e **non si presentano falsamente come rilevamenti puntuali**.

Le esecuzioni **programmate** sono disabilitate finché la variabile Actions
`V2_AUTHORIZED_FEED_CONFIRMED` non vale `true`. Il workflow può essere
lanciato manualmente per un test di configurazione senza download non
autorizzati.

Per attivare realmente il download automatico, configurare
**GitHub → Settings → Secrets and variables → Actions**:

| Tipo | Nome | Significato |
|---|---|---|
| Variable | `V2_AUTHORIZED_FEED_CONFIRMED` | `true` SOLO dopo aver verificato la licenza dati |
| Secret | `V2_FEED_NDX_URL` | URL HTTPS della catena NDX da API autorizzata |
| Secret | `V2_FEED_GLD_URL` | URL HTTPS della catena GLD da API autorizzata |
| Secret | `V2_FEED_USO_URL` | URL HTTPS della catena USO da API autorizzata |
| Secret | `V2_FEED_TOKEN` | Token Bearer, se richiesto dal provider |
| Secret | `V2_ARCHIVE_FERNET_KEY` | Chiave per cifrare snapshot negli artifact GitHub |

Genera la chiave Fernet sul TUO computer con
`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
e inseriscila nei Secrets. Non condividerla in chat.

Cboe delayed_quotes **non è** un feed autorizzato per scraping
automatico: il downloader rifiuta espressamente gli URL di quelle pagine
e i redirect verso di esse. Il formato API autorizzato deve ancora
essere verificato sul vero provider: non è stato inventato un endpoint.

Gli artifact sono salvati **cifrati**, non contengono chiavi o JSON in
chiaro, e vengono conservati 30 giorni. Il caricamento nell'app V2
richiede oggi un passaggio manuale dall'artifact GitHub; la selezione
automatica remota come SPX richiede ancora un backend separato e
autorizzato, che non può essere Supabase finché resta il blocco richiesto.

## Condizioni di validazione

La V2 richiede:
- test unitari Python superati sul ramo `v2-spx`;
- prova con una catena reale NDX/GLD/USO da Streamlit;
- prova nell'editor Pine TradingView per NQ, GC e CL;
- prova cron con feed davvero autorizzati e controllo di tre
  file `.json.gz.enc`/rilevamento.

**Non considerare attivi i download automatici prima che questi
prerequisiti siano soddisfatti.** La Serafini SPX originale è invariata.
