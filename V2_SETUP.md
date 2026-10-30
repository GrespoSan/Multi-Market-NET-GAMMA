# Multi-Market NET GAMMA V2 · clonazione architettura Serafini SPX

**Stato:** V2 in ramo di sviluppo `v2-spx`, non sostituisce la Serafini SPX esistente.
La V1 su `main` resta sospesa. L'UI principale della V2 segue la struttura
di `Serafini-SPX-Dashboard/app.py`, SENZA GEX EDGE, Replay e confronto,
Report giornaliero AI.

## Architettura

## Analisi del contesto · porting reale della SPX

La V2 non contiene più il riquadro placeholder: i pannelli della
Serafini SPX sono stati ripresi dai moduli originali e collegati al
selettore mercato.

- **Settimana ISO, Snapshot distinti, Registri**: stesso layout SPX.
  I conteggi non ancora verificabili sono indicati con «—», non si
  copiano i 13 record SPX. Il numero di registri, quando è configurato
  `V2_GITHUB_TOKEN`, è il numero di artifact della settimana, **non**
  il numero di catene opzioni realmente acquisite.
- **News e calendario macroeconomico**: `macro_calendar.py` e
  `magnificent7_earnings.py` ripresi dalla SPX. Il calendario è
  pubblico e la sua disponibilità dipende da Finance Calendar/Yahoo.
- **Volatilità precedente**: stesso schema grafico a 3 colonne SPX;
  NQ con VXN, GC con GVZ e CL con OVX (indici Cboe derivati dalle
  rispettive opzioni). **Range Daily e variazione Close/Close
  dal medesimo contratto futures reale di Massive**, mai da settlement.
  Gli indici VXN/GVZ/OVX rimangono indipendenti (Yahoo).
  Il buffer ES 10/15 punti NON è definito per NQ/GC/CL e non viene
  inventato; eventuali fonti assenti sono indicate N/D.
- **Trend Daily**: porting del metodo SPX con range, struttura, numero
  candele dello stesso colore, baricentro e candela d'impulso, applicato
  ai futures `NQ=F`, `GC=F`, `CL=F`. Solo barre precedenti alla
  data di riferimento e nessuna modifica ai calcoli NET GAMMA.
- **Apertura iniziale**: Analisi del contesto aperta prima delle 13
  di Roma, Analisi NET GAMMA chiusa per impostazione predefinita come
  nella Serafini SPX.

Il layout è allineato alla SPX, ma la disponibilità dei valori
dipende dalle fonti e dalla presenza di snapshot V2 reali. I dati
VIX/VX e il buffer specifico ES non sono copiati su mercati diversi.


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

La sezione Contesto contiene News/Calendario, volatilità VXN/GVZ/OVX e Trend Daily per NQ/GC/CL; i dati specifici SPX non vengono attribuiti ad altri mercati.

## Massive Futures · stessa fonte per Range e andamento giornaliero

La V2 interroga direttamente dal server Python l'endpoint
`GET https://api.massive.com/futures/v1/aggs/{ticker}` con barre
`resolution=1session`. Per ogni mercato sono usate **le stesse
due sessioni precedenti alla data di riferimento e lo stesso
contratto reale** per:

- **Range Daily** = High−Low; percentuale (High−Low)/Close × 100,
  visualizzata senza colore direzionale.
- **Andamento della seduta** = (Close ultimo giorno / Close giorno
  precedente − 1) × 100; verde per positivo, rosso per negativo.

Il titolo è **Andamento e volatilità — seduta precedente**; una
riga separata indica esplicitamente "Variazione chiusura della
seduta (Close/Close)". `Close` significa ultimo prezzo della
sessione Massive, **non `settlement_price`**. Il ticker, la
data e le due chiusure sono visibili in un testo di controllo.

Nei **Secrets Streamlit della V2**, oltre alle password già presenti,
configurare:

```toml
MASSIVE_API_KEY = "CHIAVE_API_PERSONALE_DA_MASSIVE"
MASSIVE_NQ_CONTRACT = "NQZ6"
MASSIVE_GC_CONTRACT = "GCZ6"
MASSIVE_CL_CONTRACT = "CLZ6"
```

Questi contratti sono **esempi riferiti a ottobre 2026**; vanno
aggiornati quando cambiano i futures attivi sui grafici
TradingView NQ1!, GC1! e CL1!. Il codice **non passa
silenziosamente** a una scadenza diversa. La chiave del plugin
Massive in ChatGPT non è trasferita automaticamente a Streamlit:
servono API key e abilitazione Futures nel proprio account.
Non condividere mai la chiave nella chat o sul repository.

L'accesso a Massive riguarda soltanto questo contesto Daily;
il NET GAMMA da Cboe, il calcolo del differenziale, la curva di
volatilità implicita e l'analisi Trend Daily rimangono
indipendenti. Se Massive non è configurato, **Range e variazione
risultano N/D**, senza sostituirli con Yahoo.
Supabase resta completamente disattivato nella V2.

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
4. Per consultare i rilevamenti cifrati direttamente dall'app, aggiungere
   nei **Secrets Streamlit** `V2_ARCHIVE_FERNET_KEY` (identica a
   GitHub Actions) e `V2_GITHUB_TOKEN` (PAT fine-grained, limitato al
   repository Multi-Market con **Actions: Read-only**). Nessuna chiave
   Supabase. Nell'espander **RILEVAMENTI CBOE** l'amministratore
   usa “Elenca rilevamenti GitHub” e “Carica fotografia ... da GitHub”.
   È disponibile anche l'upload manuale `.json.gz.enc`.

## Tre cronjob GitHub Actions

Workflow **sul ramo predefinito `main`**:
`.github/workflows/v2-spx-snapshots.yml`; effettua checkout del ramo
`v2-spx` prima di eseguire lo script. Questo permette di mantenere la V1
sospesa senza dover pubblicare o promuovere il codice V2.

Cron lunedì-venerdì, ESATTAMENTE come la Serafini SPX:
- `07:30` **Europe/Rome**, etichetta `07:30`.
- `08:50` **America/Chicago**, etichetta storica `15:50`.
- `13:30` **America/Chicago**, etichetta storica `20:30`.

In ottobre/marzo le transizioni CET/CEST e CST/CDT avvengono in
settimane diverse. Per esempio il 30 ottobre 2026 gli slot USA sono
alle **14:50 e 19:30 Roma**, dal 2 novembre ritornano **15:50 e
20:30 Roma**. Lo storico conserva i nomi logici, ma il log registra
l'ora effettiva a Roma e Chicago. Le GitHub Actions ora supportano
fusi orari IANA nello scheduler, quindi **non servono cronjob.org** per
questa V2.

La finestra di avvio valida è compresa tra l'orario nominale **nel
fuso scelto (Roma oppure Chicago)** e 12 minuti dopo. Le GitHub Actions possono partire in ritardo: i job fuori finestra
registrano uno SKIP e **non si presentano falsamente come rilevamenti puntuali**.

I **cronjob sono attivi**: il workflow GitHub Actions viene avviato
ai tre orari programmati e produce i log di stato. L'**acquisizione**
delle opzioni resta `NON_CONFIGURATO` se la variabile Actions
`V2_AUTHORIZED_FEED_CONFIRMED` non vale `true`, mancano endpoint
licenziati o la chiave di cifratura. Anche un'esecuzione manuale
può produrre solo log, senza fotografie.

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
chiaro, e vengono conservati 30 giorni. L'app V2 può
**elencarli e leggerli direttamente**, dietro accesso amministratore,
con un PAT read-only. Gli artifact `NON_CONFIGURATO` contengono
esclusivamente un log e non possono creare retroattivamente una
fotografia. Non vengono fatte chiamate a Supabase.

## Condizioni di validazione

La V2 richiede:
- test unitari Python superati sul ramo `v2-spx`;
- prova con una catena reale NDX/GLD/USO da Streamlit;
- prova nell'editor Pine TradingView per NQ, GC e CL;
- prova cron con feed davvero autorizzati e controllo di tre
  file `.json.gz.enc`/rilevamento.

**Non considerare attivi i download automatici prima che questi
prerequisiti siano soddisfatti.** La Serafini SPX originale è invariata.
