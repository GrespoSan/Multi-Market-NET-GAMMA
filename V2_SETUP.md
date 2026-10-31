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
- **Trend Daily**: struttura dei massimi/minimi, chiusura rispetto
  al baricentro, livello del baricentro, numero di candele consecutive
  dello stesso colore e ultima candela d'impulso. USA LE STESSE
  barre OHLC `1session` Massive già scaricate per la volatilità
  (NQ/GC/CL, contratto selezionato). Niente più secondi Range
  discrepanti da Yahoo, né una seconda chiamata API. Solo sedute
  precedenti alla data di riferimento e nessuna modifica ai calcoli
  NET GAMMA.
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
- `v2_storage_off.py` — zero chiamate Supabase; selettore visibile
  **Snapshot originale opzioni · archivio automatico**, con caricamento
  del rilevamento cifrato più recente e scelta di fotografie precedenti.
  Lettura consentita ad admin e lettore autenticato; override manuale
  e importazione eccezionale di file cifrati riservata all'admin.
- `v2_cron.py` — acquisizione diretta dai CDN pubblici Cboe richiesti dall'utente,
  validazione dati, archiviazione con crittografia Fernet in GitHub Actions.
  Nessun JSON opzioni non cifrato viene scritto sul disco del job.
- `gamma_chart_style.py` e `pine_spx_visual.py` — visualizzazione stile SPX.

La sezione Contesto contiene News/Calendario, volatilità VXN/GVZ/OVX e Trend Daily per NQ/GC/CL; i dati specifici SPX non vengono attribuiti ad altri mercati.

## Trend Daily — nessun duplicato del Range

Il **Range Daily precedente** in punti, percentuale e
**ESPANSIONE / COMPRESSIONE** è visibile soltanto nel primo pannello
Andamento e volatilità. Nel Trend Daily le quattro caselle ora sono:

1. **Struttura Daily**: confronto tra High/Low delle ultime due sedute
   (rialzista, ribassista, neutra/mista).
2. **Chiusura vs baricentro**: sopra/sotto `(High+Low)/2` della
   Daily precedente, con distanza percentuale.
3. **Baricentro Daily**: prezzo del punto medio della stessa candela
   Massive.
4. **Barre stesso colore**: conteggio consecutivo delle candele
   rialziste/ribassiste in base a Open/Close Massive.

Resta sotto la lettura della **candela d'impulso** sperimentale
(criterio preesistente), calcolata sulle medesime barre Massive.
L'ultimo Close e il baricentro sono verificati con la medesima
data di sessione. Ad esempio, per NQZ6 al 29/10/2026 il Close
29218,25 è **sotto** il baricentro 29452,625. Il vecchio Trend Daily
Yahoo riportava un Range 2,28% e una lettura della candela
potenzialmente divergenti: non vengono più usati.

Se manca Open nelle barre Massive o non sono presenti almeno
cinque sessioni chiuse, il Trend mostra N/D senza inventare
candele. L'archivio 75 giorni è letto attraverso la stessa
chiamata Massive (cache) della scheda Range.

## Regime da ribasso e variazione del Range Daily

Per NQ, GC e CL la lettura del contesto distingue:

- **ALTA VOLATILITÀ DA RIBASSO** quando la variazione Close/Close della
  seduta precedente è strettamente inferiore a **−1%** (es. NQ −1,81%).
  Se la soglia non scatta, non si afferma automaticamente che tutte le
  condizioni di volatilità siano basse.
- **ESPANSIONE** quando il Range percentuale (High−Low)/Close di ieri
  supera quello della sessione ancora precedente; **COMPRESSIONE** se
  è più basso, **INVARIATO** in caso di uguaglianza.
- Il Range Daily non è usato come condizione per la soglia negativa.
  Il buffer ES 10/15 punti rimane **esclusivo della SPX**, mai calcolato
  per Nasdaq, Gold o Petrolio.

Tutti i valori vengono calcolati sulle stesse due sessioni del medesimo
contratto futures Massive (non settlement e nessun fallback Yahoo).

## NET GAMMA · conformità grafica alla Serafini SPX

Per **Nasdaq, Gold e Petrolio**, la sezione ora apre con
"NET GAMMA · formula Serafini" e visualizza due grafici 0DTE/Weekly
affiancati: istogrammi NET positivi verdi/negativi rossi, medesima
scala Gamma predefinita, linea della chiusura precedente, guide
±0,5% / ±1,0% / ±1,5%, etichette dei livelli, timestamp originale
Cboe e scadenze presenti nel file. È possibile attivare la
scala indipendente per ingrandire ciascun pannello come nella SPX.
I valori Gamma reali e le regole strike/filtri di ciascun motore
preesistente rimangono invariati.

- **NDX/NDXP**: differenziale NQ−NDX automatico/modificabile;
  strike delle opzioni sull'indice convertiti soltanto per
  la visualizzazione NQ e l'esportazione Pine.
- **GLD/USO**: grafici originali degli strike ETF; soltanto il Pine
  applica una proiezione percentuale indicativa su GC/CL. Non sono
  opzioni sul future GC/CL.
- Il riferimento numerico di Serafini al 60% 0DTE e 23% Weekly
  riguarda SPX: non si finge che tali percentuali siano state
  misurate anche sugli altri tre mercati.

### Fotografie storiche selezionabili

Se nei Secrets Streamlit sono presenti `V2_GITHUB_TOKEN` (Actions:
Read-only) e `V2_ARCHIVE_FERNET_KEY`, il selettore mostra automaticamente
le acquisizioni GitHub archiviate (retention 30 giorni), propone
l'ultima ed effettua la decifratura **solo nella memoria dell'app**.
Il pulsante "Aggiorna elenco" aggiorna i registri; la modalità manuale
non viene sovrascritta. La data di rilevamento originale viene letta
dal nome della fotografia cifrata, convertita a Roma per l'orario di
download e a New York per stabilire la giornata operativa 0DTE.
Riaprire una fotografia storica NON la fa apparire come il nuovo
0DTE di oggi.

### Download programmati Cboe: NDX, GLD, USO

Il workflow `.github/workflows/v2-spx-snapshots.yml` è già installato
sul ramo predefinito `main` e lancia `v2_cron.py` da `v2-spx`.
Il runner usa direttamente gli **stessi endpoint CDN pubblici**
utilizzati dai pulsanti manuali Cboe nell'app:

- NDX: `https://cdn.cboe.com/api/global/delayed_quotes/options/_NDX.json`
- Gold (GLD): `https://cdn.cboe.com/api/global/delayed_quotes/options/GLD.json`
- Petrolio (USO): `https://cdn.cboe.com/api/global/delayed_quotes/options/USO.json`

Tre rilevamenti ogni giorno feriale: **07:30 Europe/Rome**,
**08:50 America/Chicago** e **13:30 America/Chicago** (DST automatico).
Il 30/10/2026 gli ultimi due rilevamenti sono alle 14:50 e 19:30
italiane; dal 02/11/2026 sono alle 15:50 e 20:30. I timestamp
corrispondono all'**effettiva ora di acquisizione**, mai retrodatata.

Ad ogni cron il runner esegue una sola GET HTTPS per simbolo;
non tenta bypass, proxy, login, cambio endpoint, ritentativi in caso
di HTTP 401/403/429 o elusione di limiti del provider.
Valida simbolo, struttura della catena, Gamma, Open Interest,
Volume e scadenze. I file validi sono **compressi e cifrati Fernet**
e caricati negli artifact GitHub Actions con retention di 30 giorni.
Supabase non viene chiamato.

**Unica credenziale necessaria in GitHub per archiviare:**
`V2_ARCHIVE_FERNET_KEY` come GitHub Actions Secret;
la stessa identica chiave deve essere presente nei Secrets della
nuova app Streamlit. Generarla sul proprio computer:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Per leggere l'archivio in Streamlit serve inoltre
`V2_GITHUB_TOKEN` con Actions: Read sul repository.
Non condividere in chat né nel codice alcuna chiave.
**Se manca la Fernet key, il job registra NON_CONFIGURATO e non
esegue il download.** Un run con test superati non prova un
download reale da Cboe: lo confermano solo il log `run_status.json`
e tre file `.json.gz.enc` dell'esecuzione effettiva.

Gli URL `V2_FEED_NDX_URL`, `V2_FEED_GLD_URL`,
`V2_FEED_USO_URL` non sono più richiesti. Se configurati, sono
override personalizzati e richiedono ancora la variabile
`V2_AUTHORIZED_FEED_CONFIRMED=true` per la loro sorgente.

**Avvertenza provider:** Cboe limita contrattualmente
l'acquisizione automatizzata dalle delayed quote tables e può
bloccare gli accessi. Questa attivazione è una scelta esplicita
dell'utente; il software rispetta i blocchi tecnici. In alternativa,
per un feed autorizzato esiste Cboe All Access API.

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
3. Le tre catene vengono tentate dal cron Cboe nei giorni feriali,
   purché il Secret Fernet sia configurato. Rimangono i pulsanti manuali
   per acquisizioni straordinarie e il caricamento del JSON originale.
4. Per consultare i rilevamenti cifrati direttamente dall'app, aggiungere
   nei **Secrets Streamlit** `V2_ARCHIVE_FERNET_KEY` (identica a
   GitHub Actions) e `V2_GITHUB_TOKEN` (PAT fine-grained, limitato al
   repository Multi-Market con **Actions: Read-only**). Nessuna chiave
   Supabase. Nell'espander **RILEVAMENTI CBOE** l'amministratore
   usa “Elenca rilevamenti GitHub” e “Carica fotografia ... da GitHub”.
   È disponibile anche l'upload manuale `.json.gz.enc`.
   Il selettore mostra automaticamente lo snapshot più recente.

## Cron GitHub e archivio (nessun Supabase)

I tre cron sono definiti nel workflow `main/.github/workflows/v2-spx-snapshots.yml`,
con checkout esplicito del codice `v2-spx`.
Il selettore `ULTIMO rilevamento automatico` in Streamlit legge
il nuovo artifact cifrato appena disponibile, usando
`V2_GITHUB_TOKEN` e `V2_ARCHIVE_FERNET_KEY` server-side.
La lettura delle fotografie storiche è disponibile anche agli amici
autenticati; l'importazione dei file cifrati rimane riservata all'admin.

La GitHub Action può partire in ritardo. Il runner accetta solo una
finestra di 12 minuti dallo slot pianificato; oltre registra
`FUORI_FINESTRA` senza attribuire al file un orario fittizio.
Se Cboe nega o limita l'accesso, il log segnala `ERRORE`;
se la chiave manca, `NON_CONFIGURATO`.

## Condizioni di validazione

La V2 richiede:
- test unitari Python superati sul ramo `v2-spx`;
- prova con una catena reale NDX/GLD/USO da Streamlit;
- prova nell'editor Pine TradingView per NQ, GC e CL;
- prova del workflow Cboe reale con riscontro del log di stato
  e tre file cifrati `.json.gz.enc` (NDX, GLD, USO).

**Il codice dei download programmati è attivo, ma la riuscita dipende
dalla chiave di cifratura, dall'accessibilità Cboe e dall'esecuzione
effettiva di GitHub Actions.** La Serafini SPX originale è invariata.


## Correzioni del 31/10/2026 — verifiche eseguite

**Diagnosi effettiva GitHub Actions 30/10/2026:**

- Workflow schedulato alle 18:54 UTC (id 41110865054): terminato verde
  ma `v2_cron.py` riportava `FUORI_FINESTRA`, caricando soltanto
  `run_status.json` (324 byte). Nessuna fotografia di NDX/GLD/USO.
- Workflow schedulato alle 22:35 UTC (id 41139129251): stesso problema,
  `FUORI_FINESTRA`, artifact di 323 byte, nessun download.
- Workflow manuale (id 41054963063, 30/10): `TUTTI_ARCHIVIATI`,
  **3 fotografie Cboe cifrate** NDX/GLD/USO; artifact circa 1,58 MB.
- **Causa:** GitHub può avviare gli schedule ore dopo la finestra di
  12 minuti; il precedente runner scartava tutto e restituiva codice 0.

**Correzione:** un evento `schedule` riconosciuto in ritardo sullo stesso
giorno di mercato viene elaborato, ma marcato
`GITHUB_SCHEDULE_DELAYED` e `TUTTI_ARCHIVIATI_IN_RITARDO`
se tutti i tre file sono davvero prodotti. Il timestamp del file è
l'ora reale di acquisizione, mai quella teorica. In caso di catena
assente o accesso negato l'Action fallisce (rosso), con log e codice
d'errore senza credenziali. Una esecuzione non cron fuori finestra
non può fingersi snapshot ufficiale.

L'interfaccia evidenzia `ACQUISIZIONE RITARDATA`; gli artifacts di
soli registri (sotto 1 KB) vengono filtrati dal selettore. GitHub
Actions usa fusi IANA per le tre pianificazioni, ma **non garantisce
puntualità dei runner**. Il primo esito del codice modificato richiede
una nuova esecuzione; il 31/10 è sabato e non ci sono cron del mercato.

**Parità NET GAMMA con Serafini SPX:** le tre V2 hanno due istogrammi
affiancati, riferimento/guide percentuali, stessa scala Gamma per
default, interruttori Pine `Mostra 0DTE corrente` e
`Mostra Weekly corrente` (entrambi ON). Il modulo condiviso di
estensione automatica, ON nelle tre pagine V2, legge SOLO ulteriori
strike realmente presenti nella catena Cboe già caricata. Mantiene
invariata la selezione originaria degli strike, la formula Call−Put,
i CSV originali e i rapporti NDX→NQ, GLD→GC, USO→CL. L'estensione
è limitata a 140 righe per profilo quando il nucleo è più piccolo;
un nucleo con più righe non viene troncato. **Non attribuire il
criterio SPX 25+25 o le sue percentuali 60%/23% agli ETF.**

**Limite operativo:** l'accesso automatizzato alle delayed quotes Cboe
può essere bloccato per condizioni di utilizzo; nessun bypass,
sorgente alternativa nascosta o retry elusivo è implementato.
Una garanzia contrattuale per raccolta automatica richiede un
provider/feed che autorizzi tale impiego. Nessun dato V2 su Supabase.


## cron-job.org — nuovo trigger esterno (31/10/2026)

**Motivo:** il progetto Serafini-SPX-Cloud riceve i suoi avvii
`workflow_dispatch` da cron-job.org, mentre Multi-Market V2 dipendeva
esclusivamente dal `schedule` interno GitHub, che il 30/10 ha avviato
i job 4–5 ore in ritardo. Non è un problema del suffisso Cboe
`_NDX.json` / `GLD.json` / `USO.json`: il test manuale del
30/10 ha acquisito e cifrato tutti e tre i JSON.

**Predisposizione GitHub già eseguita**:
- `main/.github/workflows/v2-spx-snapshots.yml` accetta
  `workflow_dispatch.inputs.trigger=cron-job` oltre allo `slot`.
- Il checkout resta sul ramo applicativo `v2-spx`.
- `V2_EXTERNAL_CRONJOB=true` raggiunge `v2_cron.py` e
  `v2_schedule.decision(...,external=True)`, preservando lo
  slot ufficiale (07:30, 15:50, 20:30) e l'orario di download reale.
- I test della V2 simulano tutte e tre le fasce anche nel cambio DST.
- **31/10/2026: i tre schedule interni GitHub sono stati rimossi
  dal workflow su main.** L'avvio programmato dipende esclusivamente dai
  tre job cron-job.org già verificati via HTTP 204.
  La variabile `V2_USE_EXTERNAL_CRONJOB=true` può rimanere in GitHub,
  ma non è più letta dal workflow (non serve per disattivare nulla).
  Il workflow `workflow_dispatch` resta utilizzabile manualmente per test.


**Pulizia vecchio sistema (31/10):** eliminato anche il workflow
V1 disattivato `.github/workflows/multi-market-snapshots.yml`
dal ramo `v2-spx`. I moduli Python legacy di acquisizione V1
restano inattivi e sono mantenuti soltanto per compatibilità dei test:
non esiste alcun workflow automatizzato che li richiami.
Non eliminare il workflow di test Python o gli artifact cifrati V2.

**Configurati in cron-job.org** (tre NUOVI job, mai alterare quelli SPX):
- URL POST comune:
  `https://api.github.com/repos/GrespoSan/Multi-Market-NET-GAMMA/actions/workflows/v2-spx-snapshots.yml/dispatches`
- Headers comuni: `Authorization: Bearer <PAT_FINE_GRAINED>`,
  `Accept: application/vnd.github+json`,
  `Content-Type: application/json`.
- Il PAT fine-grained GitHub deve essere circoscritto SOLO al repository
  `GrespoSan/Multi-Market-NET-GAMMA`, permission `Actions: Write`.
  Non usare il token di lettura Streamlit `V2_GITHUB_TOKEN`
  se ha permessi solo read; NON inserirlo nel codice o in chat.
- Job A: feriali lun–ven 07:30 `Europe/Rome`,
  body `{"ref":"main","inputs":{"slot":"07:30","trigger":"cron-job"}}`
- Job B: feriali lun–ven 08:50 `America/Chicago`,
  body `{"ref":"main","inputs":{"slot":"15:50","trigger":"cron-job"}}`
- Job C: feriali lun–ven 13:30 `America/Chicago`,
  body `{"ref":"main","inputs":{"slot":"20:30","trigger":"cron-job"}}`

La API GitHub restituisce risposta 204/200 quando accetta il dispatch;
questo verifica la **creazione del workflow**, non l'acquisizione.
L'esito operativo è `TUTTI_ARCHIVIATI` e 3 file
`{NDX,GLD,USO}_...json.gz.enc` negli artifacts GitHub.

**Importante:** l'account cron-job.org non è collegato a questa
integrazione GitHub. I tre job esterni non sono creati automaticamente
dalla modifica del workflow. Se il provider blocca/rifiuta il
fetch automatizzato, il runner lo segnalerà senza bypass.
