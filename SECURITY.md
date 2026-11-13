# Security

Raio-X Público is a learning project that runs on your own machine. The data it handles is public (open government data), so the main things to protect are **the database, the Airflow admin account and your machine**, not the data itself.

This document says what is protected today, what was deliberately left alone, how to rotate secrets, and what must be done before the project is exposed to the internet.

## Threat model

- **Today (local use):** the realistic risks are other machines on your network reaching the database, weak or well-known passwords, and untrusted text (a city name typed on the command line, a DAG parameter, a dashboard request) being turned into a URL or a file path.
- **If published:** anyone on the internet can use the dashboard, so anything it can do, anyone can make it do. That is a different threat model, and the checklist at the end covers it.

## What is protected today

| Area | Protection |
|---|---|
| Network exposure | Postgres (`5432`), the dashboard (`8501`) and the Airflow UI/API (`8080`) are published on `127.0.0.1` only. The Airflow metadata database and the internal services have no published port. |
| Passwords | No public defaults. `POSTGRES_PASSWORD` empty means Postgres does not start. `airflow-init` refuses to start when `AIRFLOW_FERNET_KEY`, `AIRFLOW_JWT_SECRET` or `AIRFLOW_ADMIN_PASSWORD` is empty, or when the admin password is `airflow`. |
| Secrets in git | `.env`, `.env.*` (except the example), `*.pem` and `*.key` are ignored. All tracked files and the full git history were scanned for credentials: none found. `.dockerignore` keeps `.env` out of image builds. |
| Least privilege (Airflow) | The dashboard talks to Airflow as a dedicated user with the `User` role. It can read DAGs and trigger runs; it gets `403` on connections and variables, which the `Op` role would have allowed. |
| Containers | The dashboard runs as a non-root user (uid 10001), with `cap_drop: ALL`, `no-new-privileges` and a read-only root filesystem (`/tmp` is an in-memory disk). |
| Input validation | City names, year, month and state are checked against an allow-list (`src/validacao.py`) before they become part of a URL or a file name. A slug such as `../../x` never reaches the API and never writes or reads a file. Covered by tests that fail if the validation is removed. |
| SQL | Every query that takes a value is parameterized. The dashboard's queries are fixed text. |
| Shell | The DAG builds shell commands with `shlex.quote`, and the `cidades` DAG parameter has a pattern restriction. |
| Dependencies | Versions are pinned. `pip-audit` (full dependency tree, including transitive packages) reported no known vulnerabilities for `requirements.txt` and `dashboard/requirements.txt` on the day of the review; it only knows published advisories, so this is a snapshot. Dependabot opens weekly pull requests for pip, Docker and Compose. |
| Output | The dashboard uses no `unsafe_allow_html`; everything shown is plain text or Streamlit components. |

## Rotating secrets

**Postgres password.** The `POSTGRES_PASSWORD` in `.env` is only read the first time the database is created, so changing it takes three steps:

```bash
# 1. generate a password and change it inside the database
python -c "import secrets; print(secrets.token_urlsafe(24))"
docker exec -it raio-x-publico-db psql -U raiox -d raiox_publico -c "ALTER USER raiox PASSWORD 'THE_NEW_PASSWORD';"
# 2. put the same value in .env (POSTGRES_PASSWORD) and in ~/.dbt/profiles.yml
# 3. recreate the containers so they read the new .env
docker compose --profile airflow --profile dashboard up -d
```

**Airflow admin password.** Change `AIRFLOW_ADMIN_PASSWORD` in `.env`, then (the user already exists, so the variable alone does not change it):

```bash
docker compose --profile airflow up -d
docker compose --profile airflow exec airflow-scheduler airflow users reset-password -u airflow -p THE_NEW_PASSWORD
```

**Dashboard's Airflow user.** Change `DASHBOARD_AIRFLOW_PASSWORD` in `.env` and run the same `reset-password` for the user `dashboard`.

**`AIRFLOW_JWT_SECRET`** can be changed freely (it only invalidates open sessions). **`AIRFLOW_FERNET_KEY`** encrypts values stored in Airflow's database; this project stores none, but if you ever add connections or variables, rotate it with Airflow's documented procedure instead of just replacing it.

## Known limitations (accepted for local use)

- **The dashboard connects to Postgres as `raiox`**, the database owner. Its queries are fixed and cannot be influenced by users, but a read-only role is the right design. It is on the checklist below because it matters most when the credentials leave your machine.
- **The Airflow metadata database uses the password `airflow`.** It has no published port and is reachable only from the Compose network.
- **`./src`, `./dbt`, `./airflow/dags` and `./data` are mounted read-write** into the Airflow containers (dbt and the extraction need to write to some of them), so a task could change the project files on the host. The tasks only run this repository's own code.
- **The `User` role can still read pools** (harmless here), and an Airflow account that can trigger runs can start loads (see the on-demand discussion below).
- **Base images are pinned by tag, not by digest** (`postgres:16`, `python:3.12-slim`, `apache/airflow:3.4.0-python3.12`). Dependabot proposes updates; a digest pin would make builds fully reproducible.
- **`airflow/dbt_profiles/.user.yml` was committed once** (an anonymous dbt usage id, not a credential) and is now ignored. It is still in the history; removing it would need a history rewrite and a force-push, which was judged not worth it.
- **Other databases on the same machine** (for example, other projects' Postgres containers) are outside this repository. Check that they are bound to `127.0.0.1` too.

## Before exposing it to the internet

Do not publish the current setup as is. The items below are required first:

1. **Read-only database role for the dashboard.** Create a role with `SELECT` only on `fct_despesas_mensais`, `dim_estado` and `dim_municipio`, and give only that role's credentials to the hosting platform. Remember that `dbt run` recreates tables, so grants must be reapplied (for example with dbt's `grants` config).
2. **TLS to the database.** `src/db.py` does not set `sslmode` yet; hosted Postgres (Neon, for instance) requires it. Add a `POSTGRES_SSLMODE` option and use `require` or stronger.
3. **Switch off or protect the on-demand load.** Today anyone who can open the dashboard can make it ask Airflow to hit the public TCE-SP API (limited to 5 cities and 12 months per request, with no limit on the number of requests). Publicly this is an abuse and cost vector. Disable it in the public build (a feature flag) or put authentication and a rate limit in front of it.
4. **Never expose Airflow.** Keep the Airflow UI/API off the internet. A public dashboard must not need it.
5. **Change every default** and generate new secrets for the hosted environment; do not reuse the local ones.
6. **HTTPS and a reverse proxy** (Caddy, or a platform tunnel) if you host it yourself, with no database or Airflow ports published.
7. **Backups** (`pg_dump`) and a restore test.
8. **Hide internal details in error messages.** The dashboard shows Airflow errors, including the internal service address, to the user; a public build should log them and show a generic message.
9. **Turn on GitHub's secret scanning and push protection** for the repository (Settings, Code security), and keep Dependabot enabled.

## Reporting a vulnerability

Please use GitHub's private reporting: the **Security** tab of the repository, then **Report a vulnerability**. If that is not available to you, open an issue that says you found a security problem, without exploit details, and I will get in touch.
