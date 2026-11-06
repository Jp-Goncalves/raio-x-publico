# Raio-X Público

Pipeline de dados que extrai as despesas públicas de municípios paulistas da API de transparência do TCE-SP, guarda o dado bruto no PostgreSQL, trata e modela com dbt, pronto pra alimentar um dashboard.

É um pipeline **ELT em batch**: o dado entra bruto (E, L) e só depois é transformado (T), dentro do banco. Projeto de estudo de engenharia de dados, montado como uma versão pequena do que o mercado chama de *Modern Data Stack* (extração em Python, warehouse, transformação com dbt, orquestração com Airflow).

## Arquitetura

```
API TCE-SP --extract--> data/raw/*.json --load--> raw_pagamentos (JSONB)
                                                       |
                      +--------------------------------+-----------------------------+
                      |                                                              |
           transform.py (Python, fase 1)                              dbt (SQL dentro do Postgres, fase 2)
                      |                                                              |
               stg_pagamentos                                       stg_tce_sp__despesas (view)
                                                                                     |
                                                                       fct_despesas_mensais (table)
```

A fase 1 fez a transformação em Python (`stg_pagamentos`). A fase 2 refez a mesma lógica em SQL com dbt (`stg_tce_sp__despesas`), e as duas versões foram comparadas: mesma contagem de linhas e mesma soma de valores, até o centavo. As duas coexistem de propósito, como referência.

## Stack

- Python 3.14 (testado em 3.14.7)
- PostgreSQL 16, via Docker Compose
- psycopg 3 para acesso ao banco
- dbt-core 1.12 + dbt-postgres 1.11
- Apache Airflow 3.4 (em Docker)
- Streamlit 1.67 (dashboard)

## Como rodar

Pré-requisitos: Docker e Python 3.14.

**1. Configuração e banco**

```bash
cp .env.example .env
docker compose up -d
```

O `schema.sql` é aplicado automaticamente na primeira subida, com o volume vazio. Se mudar o schema depois, recrie o volume (`docker compose down -v`) ou aplique o SQL na mão. As credenciais do `.env.example` são só de desenvolvimento local. Se a porta 5432 estiver ocupada, troque `POSTGRES_PORT` no `.env`.

**2. Dependências**

```bash
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

**3. Pipeline em Python**

Há um único ponto de entrada, `src/main.py`, com subcomandos:

| Comando | O que faz |
|---|---|
| `python src/main.py extract <cidade> <ano> <mes>` | Busca na API e salva o JSON bruto em `data/raw/` |
| `python src/main.py load <cidade> <ano> <mes>` | Carrega o JSON salvo em `raw_pagamentos` |
| `python src/main.py transform <cidade> <ano> <mes>` | Trata e grava em `stg_pagamentos` |
| `python src/main.py pipeline <cidade> <ano> <mes>` | Roda extract, load e transform em sequência |
| `python src/main.py backfill` | Roda o pipeline pra vários períodos (lista em `src/backfill.py`) |

Exemplo: `python src/main.py pipeline jacarei 2020 1`. A cidade é o nome em minúsculas, sem acento, como a API espera.

**4. dbt**

O dbt lê a conexão de `~/.dbt/profiles.yml`, que fica fora do repositório (mesma lógica do `.env`). Crie o arquivo com:

```yaml
raio_x_publico:
  target: dev
  outputs:
    dev:
      type: postgres
      host: localhost
      port: 5432
      user: raiox
      password: raiox
      dbname: raiox_publico
      schema: public
      threads: 4
```

Depois, dentro da pasta `dbt/`:

```bash
dbt debug    # confere projeto e conexão
dbt run      # constrói a view de staging e a tabela do mart
dbt test     # roda os 19 testes de qualidade
```

**5. Airflow (orquestração)**

O Airflow roda em contêineres, atrás de um *profile* do Compose, então o `docker compose up -d` simples continua subindo só o Postgres do projeto. Gere as duas chaves indicadas no `.env.example`, cole no seu `.env` e suba:

```bash
docker compose --profile airflow up -d --wait
```

A interface fica em http://127.0.0.1:8080, com usuário e senha definidos por `AIRFLOW_ADMIN_USER` e `AIRFLOW_ADMIN_PASSWORD` (`airflow`/`airflow` por padrão, só pra desenvolvimento local; a porta escuta apenas em `127.0.0.1`). A primeira subida constrói a imagem: a oficial do Airflow 3.4.0 mais um venv com o `requirements.txt`, cerca de 3,7 GB em disco. Dentro dos contêineres o banco do projeto é `postgres:5432`.

O DAG `despesas_mensais` (extract e load por cidade e mês, depois `dbt run` e `dbt test`) nasce **pausado**. Um disparo manual num DAG pausado fica na fila sem executar, então ative-o na interface antes de usar. Ao ativar, o Airflow cria na hora uma execução pro último mês agendado que ficou pra trás: ela processa o mês anterior à data de hoje e, se o TCE-SP ainda não publicou esse mês, a extração falha sem gravar nada e tenta de novo no dia seguinte, até 3 vezes.

- **Agendado:** todo dia 1º, às 06:00 (São Paulo), processa o **mês anterior** das cidades padrão (`jacarei` e `campinas`).
- **Manual:** o disparo aceita os parâmetros `cidades`, `mes_inicial` (AAAA-MM) e `quantidade_de_meses`. Por exemplo, `["jacarei"]`, `2020-03` e `3` processam março a maio de 2020 de uma cidade só. Dá pra testar sem ativar o DAG: `docker compose --profile airflow exec airflow-scheduler airflow dags test despesas_mensais -c '{"cidades":["jacarei"],"mes_inicial":"2020-03","quantidade_de_meses":3}'`.
- **Histórico:** o *backfill* do Airflow repete o schedule sobre um intervalo de datas (verificado apenas em simulação, com `dry_run`).

**6. Dashboard**

O dashboard é um app Streamlit que lê só o mart `fct_despesas_mensais`, então o Postgres precisa estar de pé e o `dbt run` já executado. Tem filtros de cidade, período e órgãos, três métricas, um gráfico de evolução mensal (uma linha por etapa do gasto), um gráfico do pago por órgão e a tabela de detalhe. Os valores de empenhado, liquidado e pago aparecem separados porque são etapas do mesmo gasto e não podem ser somados entre si.

**Em contêiner (mais simples):**

```bash
docker compose --profile dashboard up -d --build
```

Abre em http://localhost:8501. A porta é publicada só em `127.0.0.1`. O primeiro build baixa a imagem base e instala as dependências (a imagem final tem cerca de 850 MB).

**Direto na máquina**, com venv próprio, separado do do pipeline (útil pra mexer no código com recarga automática):

```bash
python -m venv dashboard/.venv
dashboard\.venv\Scripts\activate    # Linux/macOS: source dashboard/.venv/bin/activate
pip install -r dashboard/requirements.txt
streamlit run dashboard/app.py      # rode da raiz do repositório
```

Neste modo também escuta só em `127.0.0.1` (ver `.streamlit/config.toml`). Não rode os dois ao mesmo tempo: ambos usam a porta 8501.

## Estrutura

```
src/
  main.py        único ponto de entrada (subcomandos)
  pipeline.py    rodar_pipeline: extract -> load -> transform
  extract.py     chama a API, com retry, e salva o JSON bruto
  load.py        UPSERT do JSON bruto em raw_pagamentos
  transform.py   conversão de tipos e gravação em stg_pagamentos
  backfill.py    carga histórica de várias cidades e meses
  db.py          conexão com o Postgres
sql/schema.sql   tabelas raw_pagamentos e stg_pagamentos
dbt/
  models/staging/   stg_tce_sp__despesas (view) + source + testes
  models/marts/     fct_despesas_mensais (table) + testes
  tests/            testes singulares (grão único, reconciliação com o staging)
airflow/
  Dockerfile        imagem do Airflow + venv isolado com o requirements.txt
  dags/             DAG despesas_mensais
  dbt_profiles/     profile do dbt usado dentro do contêiner (lê variáveis de ambiente)
dashboard/
  app.py            app Streamlit (lê o mart fct_despesas_mensais)
  Dockerfile        imagem do dashboard (serviço `dashboard` do Compose)
  requirements.txt  dependências do dashboard, separadas das do pipeline
.streamlit/         configuração do Streamlit (sem telemetria, só localhost)
.dockerignore       o que não entra no contexto de build das imagens
docs/notes.md    comportamento da API e particularidades dos dados
data/raw/        JSONs brutos (ignorados pelo git)
```

## Decisões de projeto

- **Raw como JSONB.** A tabela raw guarda o payload exatamente como veio. Campo novo, removido ou com tipo diferente na API não quebra a carga; o problema aparece na camada de transformação, onde os testes do dbt o pegam com mensagem clara.
- **Idempotência.** O load é um UPSERT sobre `UNIQUE (cidade, periodo)`. O transform apaga e reinsere a partição inteira (cidade + período) na mesma transação, porque a API não manda id por despesa. Rodar duas vezes o mesmo período não duplica nada.
- **Retry só onde faz sentido.** Erro 5xx, falha de rede e resposta 200 com corpo que não é JSON são tentados de novo, com espera crescente. Erro 4xx falha na hora, e uma extração que falhou nunca grava arquivo.
- **Um único `main`.** Os módulos só definem funções; só o `main.py` é executável.
- **dbt.** Staging materializa como view, marts como table. Os testes cobrem `not_null`, `accepted_values` (fornecedor e evento), `relationships` e dois testes singulares (grão do mart e reconciliação com o staging).

## Particularidades dos dados

Os detalhes estão em [docs/notes.md](docs/notes.md). Os pontos que mais importam:

- A API não pagina e devolve o período inteiro de uma vez.
- Todos os campos vêm como texto, com valor em formato brasileiro (`"1266,00"`) e data em `DD/MM/AAAA`.
- A capital (São Paulo) é auditada pelo TCM-SP, não pelo TCE-SP, então a API devolve `[]` pra ela.
- O campo `evento` tem 5 valores que são **etapas do mesmo gasto**: `Empenhado`, `Valor Liquidado`, `Valor Pago`, `Reforço` e `Anulação`. Somar `vl_despesa` sem separar as etapas conta o mesmo gasto várias vezes. Use `fct_despesas_mensais`, que traz cada etapa em uma coluna própria.

## Como este projeto foi feito

Projeto de estudo, parte de um roadmap de engenharia de dados (Python, PostgreSQL, dbt, Airflow). Usei o Claude (Anthropic) como tutor e par de programação: ele escreveu boa parte do código a partir das decisões que tomamos juntos, e eu conduzi o projeto passo a passo, decidindo a arquitetura (ELT com raw em JSONB, idempotência por UPSERT e partition overwrite, um único ponto de entrada, escopo dos marts) e pedindo a explicação de cada conceito antes de seguir. Os resultados foram validados contra dados reais: a versão em dbt foi comparada com a versão em Python, e o mart é reconciliado com o staging por teste.

## Roadmap

- [x] Fase 1: extract, load e transform manuais em Python, com backfill
- [x] Fase 2: dbt com staging, mart e testes de qualidade
- [x] Fase 3: orquestração com Airflow (DAG mensal `despesas_mensais`; execução agendada e backfill real ainda não exercitados, só simulados)
- [x] Dashboard em Streamlit (filtros, gráficos e tabela; roda em contêiner pelo Compose)
