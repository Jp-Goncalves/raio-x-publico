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

## Roadmap

- [x] Fase 1: extract, load e transform manuais em Python, com backfill
- [x] Fase 2: dbt com staging, mart e testes de qualidade
- [ ] Fase 3: orquestração com Airflow (DAG mensal)
- [ ] Dashboard (Metabase ou Streamlit)
