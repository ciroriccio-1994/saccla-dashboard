# ClickAndFind Control

Modular Python application for operational controls over ClickAndFind events.

## Architecture

The data acquisition layer is isolated behind `adapters/base.py`. The current `MockClickAndFindAdapter` loads `data/mock_events.csv`. A future ClickAndFind Playwright/API adapter can replace it without changing the dashboard, rules, database, or reports.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Credentials must stay in environment variables. Do not hardcode them.

## Database Path

All components use the same `DATABASE_PATH` value:

```env
DATABASE_PATH=data/clickandfind.sqlite3
```

If `DATABASE_PATH` is not set, the default is `data/clickandfind.sqlite3`. This applies to mock checks, real checks, database diagnostics, and the Streamlit dashboard.

## Mock Mode

```bash
python3 run_check.py
```

This loads mock events, applies rules from `config/rules.yaml`, saves results to SQLite, and generates `outputs/reports/clickandfind_report.xlsx`.

## Real Single-Vehicle Mode

Run a real ClickAndFind check for one vehicle:

```bash
python3 scripts/run_real_check.py --codtrasp 9939 --date 2026-05-27
```

Operations and alarms are normalized into dashboard events. Tracking points are excluded by default. Include them explicitly with:

```bash
python3 scripts/run_real_check.py --codtrasp 9939 --date 2026-05-27 --include-tracking
```

## Dashboard

```bash
streamlit run app.py
```

The dashboard reads the same `DATABASE_PATH` used by the check scripts. After running a check, use the sidebar `Reload database` button to refresh cached data.

Inspect the active database:

```bash
python3 scripts/check_database.py
```

## Dashboard in italiano

Avviare la dashboard con:

```bash
streamlit run app.py
```

All'apertura viene mostrata la pagina **Accesso Dashboard ClickAndFind**. Inserire le stesse
credenziali usate sul portale ClickAndFind:

- username
- company
- password

La password resta solo nella sessione Streamlit corrente e non viene salvata su disco. Il logout
rimuove username, company, password e stato di autenticazione dalla sessione.

La dashboard legge il database definito da `DATABASE_PATH`; in assenza della variabile usa
`data/clickandfind.sqlite3`. Il percorso attivo e lo stato dei dati sono visibili nella sidebar.

Le sezioni principali sono:

- **Panoramica**: KPI, distribuzione delle severita, anomalie per compagnia e mezzo, mezzi a rischio.
- **Anomalie**: tabella ordinata con motivazioni e azioni suggerite.
- **Mappa eventi**: geolocalizzazione su OpenStreetMap con fallback tabellare.
- **Timeline mezzo**: sequenza temporale e dettaglio degli eventi per mezzo.
- **Dati grezzi**: tabella completa e download CSV/Excel dei dati filtrati.

Usare il pulsante **Ricarica database** dopo una nuova esecuzione della pipeline reale.

### Sincronizzazione dati da dashboard

Dopo il login, la sidebar mostra la sezione **Sincronizzazione ClickAndFind**:

- selezionare la data controllo;
- scegliere un singolo mezzo oppure abilitare **Sincronizza tutti i mezzi**;
- impostare **Numero massimo mezzi da sincronizzare**. Il default e 5 per evitare carichi eccessivi;
- premere **Avvia sincronizzazione**.

La sincronizzazione usa l'adapter interno ClickAndFind gia validato, normalizza operazioni e allarmi,
applica le regole, salva gli eventi in SQLite ed esporta un report Excel. Per sicurezza non scarica
tutto lo storico: lavora solo sulla data selezionata.

### Modalita mock e modalita reale

La modalita mock resta disponibile per test locali senza credenziali:

```bash
python3 run_check.py
```

La modalita reale da script resta disponibile per controlli tecnici o batch singolo mezzo:

```bash
python3 scripts/run_real_check.py --codtrasp 9939 --date 2026-05-27
```

La dashboard invece combina login reale, sincronizzazione guidata e visualizzazione dei dati salvati
nel database configurato.

## Regole operative ClickAndFind

Le regole operative sono configurate in `config/rules.yaml` e usano la classificazione luoghi di
`config/location_aliases.yaml`.

Controlli implementati:

- pause consentite solo in raffineria, parcheggio, deposito, pompe di benzina, officina o punti di servizio;
- stop su residuo segnalato come anomalia;
- ultimo scarico per prodotto: deve avere residuo R nera;
- ultimo scarico con stop scarico S bianca segnalato come critico;
- programmazione/carico consentiti solo in raffineria, deposito, pompe di benzina o officina;
- scarichi vietati in parcheggi, zone sospette, autostrade/tangenziali o luoghi sconosciuti;
- apertura portellone, valvole o accoppiatori consentita solo in raffineria, deposito, pompe di benzina o officina;
- possibile lavaggio quando il portellone resta aperto in parcheggio oltre la soglia configurata.

La soglia lavaggio e configurabile:

```yaml
suspected_washing:
  door_opening_parking_duration_threshold_minutes: 5
```

L'indice vie include Napoli, Roma e Sicilia con tipi standard:

- `parking`
- `refinery`
- `depot`
- `gas_station`
- `workshop`
- `service_area`
- `suspicious`
- `unknown`

La dashboard italiana include tab dedicate:

- **Controlli operativi**
- **Ultimi scarichi**
- **Luoghi e vie**
- **Possibili lavaggi**

## Gestione luoghi dalla dashboard

Il tab **Gestione luoghi** permette di amministrare `config/location_aliases.yaml` senza modificare
manualmente il file.

- Per aggiungere una nuova via, aprire **Aggiungi nuovo luogo**, compilare stringa di ricerca,
  tipo luogo, etichetta ed eventuali note, quindi premere **Aggiungi luogo**.
- Per cambiare classificazione, aprire **Modifica luogo esistente**, selezionare l'alias e modificare
  il tipo luogo o gli altri campi.
- Per escludere temporaneamente un alias senza eliminarlo, usare **Disattiva luogo**. Gli alias
  disattivati vengono ignorati dal classificatore.
- Per verificare un indirizzo, aprire **Test classificazione luogo**, inserire il testo e premere
  **Testa classificazione**. La dashboard mostra tipo, etichetta, alias, confidenza, fonte e note.

La priorita piu bassa viene valutata per prima. Prima di ogni salvataggio viene creato automaticamente
un backup `config/location_aliases.backup_YYYYMMDD_HHMMSS.yaml`. Se il YAML e malformato, la dashboard
mostra l'errore e non sovrascrive il file originale.

## Gestione regole dalla dashboard

Il tab **Gestione regole** permette di amministrare `config/rules.yaml` senza modificare
manualmente il file.

- In **Aggiungi nuova regola** si definiscono ID, nome, severita, categoria, tipi evento,
  luoghi consentiti/vietati, condizioni, spiegazione, azione e priorita.
- In **Modifica regola esistente** si puo cambiare la severita e ogni altro parametro,
  disattivare o riattivare la regola oppure eliminarla con conferma.
- In **Soglie operative** si configurano durata possibile lavaggio, pausa lunga e pausa minima.
- In **Test regole** si costruisce un evento simulato e si visualizzano severita finale,
  punteggio rischio, regole applicate, motivazioni e azioni suggerite.

Le regole disattivate vengono ignorate dal motore. Se piu regole corrispondono allo stesso evento,
il sistema conserva tutti gli ID e assegna la severita piu alta. Prima di ogni salvataggio viene
creato `config/rules.backup_YYYYMMDD_HHMMSS.yaml`. In caso di YAML malformato, la dashboard mostra
un errore e non sovrascrive il file originale.

## Network Inspection

Before implementing real scraping, inspect whether ClickAndFind exposes usable internal XHR/fetch endpoints:

```bash
python3 scripts/inspect_network.py
```

The script loads credentials from `.env`, opens Chromium, tries to log in with selectors from `config/selectors.yaml`, and falls back to manual login if selectors are missing or fail. Keep the browser open and manually navigate through company selection, vehicle search, Carichi e Scarichi, Operazioni, and Allarmi. Press ENTER in the terminal when finished.

Outputs are saved locally:

- `outputs/network_logs/network_summary.csv`
- `outputs/network_logs/relevant_endpoints.csv`
- `outputs/network_logs/json_responses/`
- `outputs/network_logs/xml_responses/`
- `outputs/network_logs/text_responses/`
- `outputs/screenshots/network_inspection_start.png`
- `outputs/screenshots/network_inspection_end.png`

Analyze captured network logs:

```bash
python3 scripts/analyze_network_logs.py
```

## Internal API Diagnostic

After confirming the portal endpoints, test authenticated internal API calls without DOM scraping:

```bash
python3 scripts/test_internal_api_adapter.py --codtrasp 9939 --date 2026-05-27
```

The adapter uses Playwright only to obtain an authenticated session. Raw responses are saved in `outputs/raw_api_responses/`, and normalized diagnostic CSVs are saved in `outputs/api_diagnostics/`.

Inspect saved raw API responses:

```bash
python3 scripts/inspect_raw_api_responses.py
```

Regenerate internal endpoint configuration from captured network traffic:

```bash
python3 scripts/extract_internal_endpoints.py
```

The adapter prefers exact full URLs discovered in `outputs/network_logs/relevant_endpoints.csv` and falls back to `config/internal_endpoints.yaml`.

Login behavior is controlled by `LOGIN_MODE`:

- `human_like`: slowly types credentials and waits for the application to initialize.
- `auto`: uses the faster form-fill login.
- `manual`: waits for the user to log in and press ENTER.

Compare automatic and manual login network initialization:

```bash
python3 scripts/diagnose_manual_login.py
python3 scripts/compare_login_network.py
```
