# Raio-X Público

**English** | [Português](README.pt-BR.md)

*Raio-X Público* means "public X-ray". It is a data pipeline that extracts public spending data for municipalities in the state of São Paulo (Brazil) from the TCE-SP transparency API, stores the raw data in PostgreSQL, cleans and models it with dbt, and serves it through a dashboard.

It is a **batch ELT pipeline**: data lands raw first (extract, load) and is transformed afterwards, inside the database. It is a learning project in data engineering, built as a small version of what the industry calls the *Modern Data Stack*: extraction in Python, a warehouse, transformation with dbt, orchestration with Airflow.

> Code comments, dbt model descriptions and [docs/notes.md](docs/notes.md) are written in Portuguese. A full Portuguese version of this README is in [README.pt-BR.md](README.pt-BR.md).

## Architecture

```
TCE-SP API --extract--> data/raw/*.json --load--> raw_pagamentos (JSONB, key: IBGE code + period)
                                                       |
                      +--------------------------------+-----------------------------+
                      |                                                              |
           transform.py (Python, phase 1)                              dbt (SQL inside Postgres, phase 2)
                      |                                                              |
               stg_pagamentos                                       stg_tce_sp__despesas (view)
                                                                                     |
                                                                       fct_despesas_mensais (table)
                                                                                     |
IBGE --> raw_ibge_municipios --+                                                     +--> dashboard / DAG
TCE-SP --> raw_tce_sp_municipios --+--> dbt --> dim_estado, dim_municipio (IBGE code <-> API name)
```

Phase 1 did the transformation in Python (`stg_pagamentos`). Phase 2 redid the same logic in SQL with dbt (`stg_tce_sp__despesas`), and the two versions were compared: same row count and same sum of values, to the cent. Both are kept on purpose, as a reference.

## Stack

- Python 3.14 (tested on 3.14.7)
- PostgreSQL 16, via Docker Compose
- psycopg 3 for database access
- dbt-core 1.12 + dbt-postgres 1.11
- Apache Airflow 3.4 (in Docker)
- Streamlit 1.67 (dashboard)

## How to run

Prerequisites: Docker and Python 3.14.

**1. Configuration and database**

```bash
cp .env.example .env
# edit .env and fill in POSTGRES_PASSWORD (the command to generate a strong password is in the file itself)
docker compose up -d
```

The password is mandatory and there is no default: with an empty `POSTGRES_PASSWORD`, Postgres will not even start. The database listens on `127.0.0.1` only (your own machine), not on the network. `schema.sql` is applied automatically on the first start, when the volume is empty. If you change the schema later, recreate the volume (`docker compose down -v`) or apply the SQL by hand. If port 5432 is taken, change `POSTGRES_PORT` in `.env`. More on security in [SECURITY.md](SECURITY.md).

**2. Dependencies**

```bash
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

**3. dbt: connection**

dbt reads its connection from `~/.dbt/profiles.yml`, which lives outside the repository (same idea as `.env`). Create the file with the content below, replacing the password with the same `POSTGRES_PASSWORD` you put in `.env`:

```yaml
raio_x_publico:
  target: dev
  outputs:
    dev:
      type: postgres
      host: localhost
      port: 5432
      user: raiox
      password: PASTE_THE_POSTGRES_PASSWORD_FROM_ENV_HERE
      dbname: raiox_publico
      schema: public
      threads: 4
```

**4. Municipalities (required before loading expenses)**

The raw expenses table is keyed by the municipality's **IBGE code** (7 digits), not by its name, because names repeat across states (there are many "Bom Jesus"). What you type in the commands is still the name the TCE-SP API expects (`jacarei`: lowercase, no accents); `load` translates it into the code through `dim_municipio`. That is why the dimension must exist before the first `load`:

```bash
python src/main.py municipios SP        # the state's municipalities (IBGE localities API)
python src/main.py municipios-tce-sp    # the ones TCE-SP covers, with the name the API expects
cd dbt && dbt run                       # builds dim_estado and dim_municipio
```

`dim_municipio` has all 645 municipalities of SP; the `slug_tce_sp` column is filled for the 644 that TCE-SP covers and empty for the state capital, which is audited by TCM-SP instead. The match is only valid for SP, so a repeated name in another state cannot match by mistake. Municipalities rarely change, so they stay out of the monthly pipeline: run these again only to refresh them. Trying to load expenses before this fails with a message telling you what to run.

*Already had a database from before this change?* The key of `raw_pagamentos` used to be the city name. Once the dimension is built, apply the migration once (it is transactional, backs the table up, and is safe to repeat), then run `dbt run`:

```bash
docker exec -i raio-x-publico-db psql -U raiox -d raiox_publico -v ON_ERROR_STOP=1 < sql/migracoes/001_chave_codigo_ibge.sql
```

**5. Python pipeline**

There is a single entry point, `src/main.py`, with subcommands:

| Command | What it does |
|---|---|
| `python src/main.py extract <city> <year> <month>` | Fetches from the API and saves the raw JSON in `data/raw/` |
| `python src/main.py load <city> <year> <month>` | Loads the saved JSON into `raw_pagamentos` (translates the name into the IBGE code through the dimension) |
| `python src/main.py transform <city> <year> <month>` | Cleans the data and writes it to `stg_pagamentos` |
| `python src/main.py pipeline <city> <year> <month>` | Runs extract, load and transform in sequence |
| `python src/main.py backfill <year> <city> [<city> ...]` | Runs the pipeline for the 12 months of a year, for one or more cities (validated against the dimension) |
| `python src/main.py cidades [<city> ...]` | Prints (JSON) the cities to process: the ones given (validated) or, with none, the ones already loaded. Used by the DAG |
| `python src/main.py municipios <UF>` | Loads a state's municipalities (IBGE API) into `raw_ibge_municipios` |
| `python src/main.py municipios-tce-sp` | Loads the list of municipalities TCE-SP covers into `raw_tce_sp_municipios` |

Example: `python src/main.py pipeline jacarei 2020 1`. After loading expenses, rebuild the models and run the quality tests, inside the `dbt/` folder:

```bash
dbt debug    # checks the project and the connection
dbt run      # builds staging, mart and dimensions
dbt test     # runs the 47 data quality tests
```

**6. Airflow (orchestration)**

Airflow runs in containers behind a Compose *profile*, so a plain `docker compose up -d` still starts only the project's Postgres. Generate the two keys and the admin password described in `.env.example` (`AIRFLOW_FERNET_KEY`, `AIRFLOW_JWT_SECRET`, `AIRFLOW_ADMIN_PASSWORD`), paste them into your `.env`, and start it:

```bash
docker compose --profile airflow up -d --wait
```

The UI is at http://127.0.0.1:8080, with the user and password set by `AIRFLOW_ADMIN_USER` and `AIRFLOW_ADMIN_PASSWORD` (the password is mandatory and has no default: `airflow-init` refuses to start if it, `AIRFLOW_FERNET_KEY` or `AIRFLOW_JWT_SECRET` is empty, or if the password is `airflow`; the port listens on `127.0.0.1` only). The first start builds the image: the official Airflow 3.4.0 image plus a venv with `requirements.txt`, about 3.7 GB on disk. Inside the containers, the project's database is `postgres:5432`.

The `despesas_mensais` DAG (extract and load per city and month, then `dbt run` and `dbt test`) is created **paused**. A manual trigger on a paused DAG sits in the queue without running, so enable it in the UI before using it (the dashboard's on-demand load also needs it enabled). When you enable it, Airflow sometimes immediately creates a run for the last scheduled month that was left behind (it happened on the first activation, not on a later one): that run processes the month three months before its date and, if TCE-SP has not published that month yet, the extraction fails without writing anything and retries the next day, up to 3 times.

- **Scheduled:** on the 1st of every month at 06:00 (São Paulo time), it processes the month **three months before** the run (the `MESES_DE_DEFASAGEM` constant in the DAG) for the cities that **have already been loaded** (with real data: there is no fixed list in the DAG). It is not the previous month because TCE-SP publishes with a delay: on 2026-11-06 both cities had September, but October and November came back empty.
- **Manual:** the trigger accepts the parameters `cidades` (one or more; empty = the ones already loaded), `mes_inicial` (YYYY-MM) and `quantidade_de_meses`. The chosen cities are validated against `dim_municipio`: only a city TCE-SP covers is accepted, otherwise the run fails right away, listing the invalid ones. For example, `["jacarei"]`, `2020-03` and `3` process March to May 2020 for a single city. You can test without enabling the DAG: `docker compose --profile airflow exec airflow-scheduler airflow dags test despesas_mensais -c '{"cidades":["jacarei"],"mes_inicial":"2020-03","quantidade_de_meses":3}'`.
- **History:** Airflow's *backfill* repeats the schedule over a date range (only verified in simulation, with `dry_run`).

**7. Dashboard**

The dashboard is a Streamlit app that reads the `fct_despesas_mensais` mart and the `dim_estado` and `dim_municipio` dimensions (municipalities are identified by IBGE code, and the names come from the dimension), so Postgres must be up and `dbt run` already executed. The filters, in the sidebar:

- **State:** comes from the dimensions (`dim_estado`); for now only SP, the only state with municipalities covered by the source.
- **Cities:** multi-select with the state's municipalities covered by TCE-SP (`dim_municipio`). It opens with **no city selected**, in alphabetical order (accents ignored), with no distinction between cities that already have data and cities that do not. Choosing a city with no data for the period triggers the on-demand load (see below). The values of the chosen cities are added up.
- **Period:** a date picker that opens **three months before today** (the source publishes with a delay, so the current month would be empty) and goes from January 2014 to today. **The day is not taken into account**: the source is monthly, so only month and year count (15/01 to 10/03 means January, February and March in full). This is stated in the form, in the field's help text and in the result caption ("Período: Janeiro/2020 a Março/2020, meses inteiros"). Streamlit has no month-and-year-only picker, so a date picker it is for now. January 2014 is the first month the source has for all 11 cities tested (Jacareí has all of 2013 empty); a city that starts later just has its own months skipped, and the screen says which.
- **Confirm:** cities and period live inside a form: changing them does not change the screen, only the **Confirmar** button applies them. The state is outside the form (the cities depend on it) and the agency filter comes after, already working on what was confirmed.

**On-demand load.** When you confirm a city and a period with no loaded data, the dashboard **does not write to the database**: it asks Airflow, through its API, for a run of the `despesas_mensais` DAG for just that city and those months. The screen shows progress ("queued", "running"), polls Airflow every 5 seconds and refreshes by itself when the load finishes. While a load is running, the **Confirmar button is disabled** (so nobody fires repeated requests), and the chosen cities and period **stay** in the filters after the result. What this requires and how it behaves:

- **Airflow must be up** (`--profile airflow`) and the DAG **enabled** (not paused); otherwise the screen says what to do, instead of queuing a request that never runs.
- The dashboard uses a **restricted Airflow user** (`DASHBOARD_AIRFLOW_USER`, role `User`: it triggers runs, but cannot read or change connections and variables, which the `Op` role would allow), and not the administrator. `airflow-init` creates the user when `DASHBOARD_AIRFLOW_PASSWORD` is set in `.env`.
- **Limits per request**: up to 5 cities and 12 months; above that the screen explains and triggers nothing. There is no date ceiling: asking for a month the source has not published yet is allowed, the API answers `[]`, the task is skipped (exit code 99) and the screen says which cities and months had no data. Without the limits, "Select all" (644 cities) would fire thousands of calls at the public API.
- **No duplicate requests**: a request has a deterministic identifier (cities, first month and count), and Airflow rejects a repeated one. Two clicks, or two people asking for the same thing, follow the same run. If it failed, the **Tentar de novo** button creates a new one. Anyone who does not want to wait uses **Parar de acompanhar**: the load keeps going in Airflow, the Confirmar button unlocks, and **Acompanhar de novo** resumes following it.
- A city loaded once **joins the monthly update** of the DAG (which updates the cities already loaded), with no limit on how many.
- **A month the source does not have for that city** is not an error: in an on-demand (or manual) run that combination is **skipped immediately**, without waiting and without bringing the request down. The other combinations go on, `dbt run` runs with what worked, and the screen says exactly which months of which cities had no data. (In the **scheduled** run it keeps failing and retrying the next day, because there the month is usually just late.)
- If a step **really fails**, `dbt run` still runs with what was loaded, and the run ends as a failure (the `conferir` task fails on purpose) instead of looking like a success. A real API error can take days to show up as a failure because of the retries; the **Parar de acompanhar** button exists for that.

The screen has three metrics, a monthly evolution chart (one line per stage of the spending, or side-by-side bars when only one month is selected), a chart of the amount paid per agency (the color shows the city) and the detail table. To load one more city, run the pipeline or the DAG for it. The dashboard needs the dimensions ready: run `municipios SP`, `municipios-tce-sp` and `dbt run` first. The committed (*empenhado*), settled (*liquidado*) and paid (*pago*) amounts are shown separately because they are stages of the same expense and must not be added to each other.

**In a container (simpler):**

```bash
docker compose --profile dashboard up -d --build
```

It opens at http://localhost:8501. The port is published on `127.0.0.1` only. The first build downloads the base image and installs the dependencies (the final image is about 850 MB). The container runs as a regular user, with no Linux capabilities, no new privileges and a read-only filesystem.

**Directly on your machine**, with its own venv, separate from the pipeline's (useful for editing the code with auto-reload):

```bash
python -m venv dashboard/.venv
dashboard\.venv\Scripts\activate    # Linux/macOS: source dashboard/.venv/bin/activate
pip install -r dashboard/requirements.txt
streamlit run dashboard/app.py      # run from the repository root
```

In this mode it also listens on `127.0.0.1` only (see `.streamlit/config.toml`). Do not run both at once: they use the same port, 8501.

## Tests

Two levels, which test different things:

```bash
python -m unittest discover -s tests -t . -b    # Python code: 49 tests, no database or network
cd dbt && dbt test                               # data: 47 tests, in Postgres
```

The Python tests cover value and date conversions, retry (5xx and invalid bodies are retried, 4xx fails immediately), the "month without data" rule (skip in the on-demand load, fail in the scheduled one), city validation, the rejection of malicious input (a slug like `../../x` never reaches the API or writes a file), and the Airflow client (a request with a fixed identifier, and what to do when Airflow rejects a repeated id). They need no dependency beyond those in `requirements.txt`.

## Structure

```
src/
  main.py        single entry point (subcommands)
  pipeline.py    rodar_pipeline: extract -> load -> transform
  api_client.py  GET with retry and backoff, shared by both APIs
  airflow_client.py  Airflow API: the dashboard requests on-demand loads through it
  extract.py     calls the expenses API and saves the raw JSON
  municipios.py  loads the IBGE municipalities and the TCE-SP list into the raw tables
  load.py        UPSERT of the raw JSON into raw_pagamentos
  transform.py   type conversion and writing to stg_pagamentos
  backfill.py    historical load of a whole year, for the cities given
  db.py          Postgres connection
  validacao.py   validates what becomes a URL or a file name (city, year, month, state)
sql/schema.sql   tables raw_pagamentos, raw_ibge_municipios, raw_tce_sp_municipios and stg_pagamentos
sql/migracoes/   migrations for databases that already existed (001: raw_pagamentos key becomes the IBGE code)
tests/           unit tests for the Python code (unittest, no database or network)
dbt/
  models/staging/   stg_tce_sp__despesas, stg_ibge__municipios and stg_tce_sp__municipios (views) + sources + tests
  models/marts/     fct_despesas_mensais, dim_estado and dim_municipio (tables) + tests
  tests/            singular tests (unique grain, reconciliations with staging and raw, IBGE code x state, unique slug per state)
airflow/
  Dockerfile        Airflow image + isolated venv with requirements.txt
  dags/             the despesas_mensais DAG
  dbt_profiles/     dbt profile used inside the container (reads environment variables)
dashboard/
  app.py            Streamlit app (reads the fct_despesas_mensais mart and the location dimensions)
  Dockerfile        dashboard image (the `dashboard` Compose service); runs as a regular user, not root
  requirements.txt  dashboard dependencies, separate from the pipeline's
.streamlit/         Streamlit configuration (no telemetry, localhost only)
.dockerignore       what stays out of the images' build context
.github/dependabot.yml  weekly alerts for new versions and security fixes in dependencies
SECURITY.md         what is protected, what is missing before going public, and how to rotate secrets
docs/notes.md    API behavior and data quirks (in Portuguese)
data/raw/        raw JSON files (ignored by git)
```

## Design decisions

- **Raw as JSONB.** The raw table stores the payload exactly as it arrived. A new, removed or differently typed field in the API does not break the load; the problem shows up in the transformation layer, where dbt's tests catch it with a clear message.
- **Idempotency.** The load is an UPSERT on `UNIQUE (codigo_ibge, periodo)`. The transform deletes and reinserts the whole partition (municipality + period, which is one raw row) in the same transaction, because the API sends no id per expense. Running the same period twice duplicates nothing.
- **Retry only where it makes sense.** A 5xx error, a network failure and a 200 response whose body is not JSON are retried with growing waits. A 4xx error fails immediately, and an extraction that failed never writes a file.
- **A single `main`.** The modules only define functions; only `main.py` is executable.
- **The municipality is identified by IBGE code.** Names repeat across states ("Bom Jesus"), so the key of raw, staging and mart is the 7-digit code. The name the TCE-SP API expects (`slug`) lives only at the edges (command line, DAG parameters, file names in `data/raw`) and in `dim_municipio`, which does the translation. When the first new state arrives, raw and models are already ready for it; all that is missing is an expenses source for it.
- **dbt.** Staging materializes as views, marts as tables. The tests cover `not_null`, `accepted_values` (supplier and event), `relationships` (including expense → municipality), and singular tests: mart grain, reconciliation with staging **per municipality and period** (a grand total would not catch values swapped between cities), IBGE code × state, and unique slug per state.
- **Two levels of tests.** dbt tests the **data**; `tests/` tests the **Python code** (conversions, retry, "month without data" rules, city validation, the Airflow client).
- **Validate at the edges, with an allow-list.** City, year, month and state become part of a URL or a file name, so they are checked against what is known to be valid (`src/validacao.py`) before use. There is no list of forbidden characters to forget one from.

## Security

The project is designed to run on your own machine: everything listens on `127.0.0.1` only, passwords are mandatory (there is no public default), the dashboard container runs without root, without extra capabilities and with a read-only filesystem, the dashboard talks to Airflow through a user with the `User` role, and everything that becomes a URL or a file name is validated. Dependencies are pinned and have no known vulnerabilities. What is still missing before publishing on the internet (a read-only database user, SSL, protection of the on-demand load) is in [SECURITY.md](SECURITY.md).

## Data quirks

The details are in [docs/notes.md](docs/notes.md) (in Portuguese). The points that matter most:

- The API does not paginate and returns the whole period at once.
- All fields arrive as text, with values in Brazilian format (`"1266,00"`) and dates as `DD/MM/YYYY`.
- The state capital (São Paulo) is audited by TCM-SP, not TCE-SP, so the API returns `[]` for it.
- The `evento` field has 5 values that are **stages of the same expense**: `Empenhado`, `Valor Liquidado`, `Valor Pago`, `Reforço` and `Anulação`. Adding up `vl_despesa` without separating the stages counts the same expense several times. Use `fct_despesas_mensais`, which has each stage in its own column.

## How this project was made

A learning project, part of a data engineering roadmap (Python, PostgreSQL, dbt, Airflow). I used Claude (Anthropic) as a tutor and pair programmer: it wrote a good part of the code from the decisions we made together, and I drove the project step by step, deciding the architecture (ELT with raw in JSONB, idempotency through UPSERT and partition overwrite, a single entry point, the scope of the marts) and asking for an explanation of each concept before moving on. The results were validated against real data: the dbt version was compared with the Python version, and the mart is reconciled with staging by a test.

## Roadmap

- [x] Phase 1: manual extract, load and transform in Python, with backfill
- [x] Phase 2: dbt with staging, mart and quality tests
- [x] Phase 3: orchestration with Airflow (monthly `despesas_mensais` DAG; scheduled run and real backfill not yet exercised, only simulated)
- [x] Streamlit dashboard (filters, charts and table; runs in a container through Compose)
- [x] Municipality catalog (IBGE) and raw key by IBGE code
- [x] On-demand load from the dashboard (through the Airflow API)
- [x] Security hardening (local-first defaults, input validation, least-privilege Airflow user; see [SECURITY.md](SECURITY.md))
- [ ] Public deployment (free tier first; see the checklist in [SECURITY.md](SECURITY.md))
- [ ] Other states: raw and models are ready, but each state needs its own expenses source (each audit court has a different API, and none has been verified)
- [ ] Real scheduled run and Airflow backfill: only simulated so far
- [ ] Month-and-year-only picker in the dashboard (today it is a date picker in which the day is ignored)
