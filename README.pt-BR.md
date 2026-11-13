# Raio-X Público

[English](README.md) | **Português**

Pipeline de dados que extrai as despesas públicas de municípios paulistas da API de transparência do TCE-SP, guarda o dado bruto no PostgreSQL, trata e modela com dbt, pronto pra alimentar um dashboard.

É um pipeline **ELT em batch**: o dado entra bruto (E, L) e só depois é transformado (T), dentro do banco. Projeto de estudo de engenharia de dados, montado como uma versão pequena do que o mercado chama de *Modern Data Stack* (extração em Python, warehouse, transformação com dbt, orquestração com Airflow).

## Arquitetura

```
API TCE-SP --extract--> data/raw/*.json --load--> raw_pagamentos (JSONB, chave: código IBGE + período)
                                                       |
                      +--------------------------------+-----------------------------+
                      |                                                              |
           transform.py (Python, fase 1)                              dbt (SQL dentro do Postgres, fase 2)
                      |                                                              |
               stg_pagamentos                                       stg_tce_sp__despesas (view)
                                                                                     |
                                                                       fct_despesas_mensais (table)
                                                                                     |
IBGE --> raw_ibge_municipios --+                                                     +--> dashboard / DAG
TCE-SP --> raw_tce_sp_municipios --+--> dbt --> dim_estado, dim_municipio (código IBGE <-> nome da API)
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
# edite o .env e preencha POSTGRES_PASSWORD (o comando pra gerar uma senha forte está no próprio arquivo)
docker compose up -d
```

A senha é obrigatória e não há valor padrão: com `POSTGRES_PASSWORD` vazia o Postgres nem sobe. O banco só escuta em `127.0.0.1` (a própria máquina), não na rede. O `schema.sql` é aplicado automaticamente na primeira subida, com o volume vazio. Se mudar o schema depois, recrie o volume (`docker compose down -v`) ou aplique o SQL na mão. Se a porta 5432 estiver ocupada, troque `POSTGRES_PORT` no `.env`. Mais sobre segurança em [SECURITY.md](SECURITY.md).

**2. Dependências**

```bash
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

**3. dbt: conexão**

O dbt lê a conexão de `~/.dbt/profiles.yml`, que fica fora do repositório (mesma lógica do `.env`). Crie o arquivo com o conteúdo abaixo, trocando a senha pela mesma `POSTGRES_PASSWORD` do `.env`:

```yaml
raio_x_publico:
  target: dev
  outputs:
    dev:
      type: postgres
      host: localhost
      port: 5432
      user: raiox
      password: COLE_AQUI_A_POSTGRES_PASSWORD_DO_ENV
      dbname: raiox_publico
      schema: public
      threads: 4
```

**4. Municípios (obrigatório antes de carregar despesas)**

O raw de despesas é identificado pelo **código IBGE** do município (7 dígitos), e não pelo nome, porque o nome se repete entre estados (há vários "Bom Jesus"). O que você digita nos comandos continua sendo o nome que a API do TCE-SP espera (`jacarei`: minúsculas, sem acento); o `load` o traduz em código pela `dim_municipio`. Por isso a dimensão precisa existir antes do primeiro `load`:

```bash
python src/main.py municipios SP        # municípios do estado (API de localidades do IBGE)
python src/main.py municipios-tce-sp    # os que o TCE-SP atende, com o nome que a API espera
cd dbt && dbt run                       # monta dim_estado e dim_municipio
```

A `dim_municipio` tem os 645 municípios de SP; a coluna `slug_tce_sp` fica preenchida nos 644 que o TCE-SP atende e vazia na capital, que é auditada pelo TCM-SP. O cruzamento só vale pra SP, pra um nome repetido em outro estado não casar por engano. Os municípios mudam raramente, então ficam fora do pipeline mensal: rode de novo só se quiser atualizar. Tentar carregar despesas antes disso falha com uma mensagem que diz o que rodar.

*Banco que já existia antes dessa mudança?* A chave de `raw_pagamentos` era o nome da cidade. Com a dimensão construída, aplique a migração uma vez (é transacional, faz cópia de segurança da tabela e é seguro repetir) e depois rode `dbt run`:

```bash
docker exec -i raio-x-publico-db psql -U raiox -d raiox_publico -v ON_ERROR_STOP=1 < sql/migracoes/001_chave_codigo_ibge.sql
```

**5. Pipeline em Python**

Há um único ponto de entrada, `src/main.py`, com subcomandos:

| Comando | O que faz |
|---|---|
| `python src/main.py extract <cidade> <ano> <mes>` | Busca na API e salva o JSON bruto em `data/raw/` |
| `python src/main.py load <cidade> <ano> <mes>` | Carrega o JSON salvo em `raw_pagamentos` (traduz o nome em código IBGE pela dimensão) |
| `python src/main.py transform <cidade> <ano> <mes>` | Trata e grava em `stg_pagamentos` |
| `python src/main.py pipeline <cidade> <ano> <mes>` | Roda extract, load e transform em sequência |
| `python src/main.py backfill <ano> <cidade> [<cidade> ...]` | Roda o pipeline pros 12 meses de um ano, pra uma ou mais cidades (validadas pela dimensão) |
| `python src/main.py cidades [<cidade> ...]` | Imprime (JSON) as cidades a processar: as informadas (validadas) ou, sem nenhuma, as que já foram carregadas. Usado pelo DAG |
| `python src/main.py municipios <UF>` | Carrega os municípios de uma UF (API do IBGE) em `raw_ibge_municipios` |
| `python src/main.py municipios-tce-sp` | Carrega a lista de municípios que o TCE-SP atende em `raw_tce_sp_municipios` |

Exemplo: `python src/main.py pipeline jacarei 2020 1`. Depois de carregar despesas, reconstrua os modelos e rode os testes de qualidade, dentro da pasta `dbt/`:

```bash
dbt debug    # confere projeto e conexão
dbt run      # constrói staging, mart e dimensões
dbt test     # roda os 47 testes de qualidade
```

**6. Airflow (orquestração)**

O Airflow roda em contêineres, atrás de um *profile* do Compose, então o `docker compose up -d` simples continua subindo só o Postgres do projeto. Gere as duas chaves e a senha do admin indicadas no `.env.example` (`AIRFLOW_FERNET_KEY`, `AIRFLOW_JWT_SECRET`, `AIRFLOW_ADMIN_PASSWORD`), cole no seu `.env` e suba:

```bash
docker compose --profile airflow up -d --wait
```

A interface fica em http://127.0.0.1:8080, com usuário e senha definidos por `AIRFLOW_ADMIN_USER` e `AIRFLOW_ADMIN_PASSWORD` (a senha é obrigatória e não há padrão: o `airflow-init` se recusa a subir se ela, a `AIRFLOW_FERNET_KEY` ou a `AIRFLOW_JWT_SECRET` estiverem vazias, ou se a senha for `airflow`; a porta escuta apenas em `127.0.0.1`). A primeira subida constrói a imagem: a oficial do Airflow 3.4.0 mais um venv com o `requirements.txt`, cerca de 3,7 GB em disco. Dentro dos contêineres o banco do projeto é `postgres:5432`.

O DAG `despesas_mensais` (extract e load por cidade e mês, depois `dbt run` e `dbt test`) nasce **pausado**. Um disparo manual num DAG pausado fica na fila sem executar, então ative-o na interface antes de usar (a carga sob demanda do dashboard também precisa dele ativo). Ao ativar, o Airflow às vezes cria na hora uma execução pro último mês agendado que ficou pra trás (na primeira ativação aconteceu, numa ativação posterior não): ela processa o mês de três meses antes da data dessa execução e, se o TCE-SP ainda não publicou esse mês, a extração falha sem gravar nada e tenta de novo no dia seguinte, até 3 vezes.

- **Agendado:** todo dia 1º, às 06:00 (São Paulo), processa o mês de **três meses antes** da execução (constante `MESES_DE_DEFASAGEM` no DAG) das cidades que **já foram carregadas** (com dado de verdade: não há lista fixa no DAG). Não é o mês anterior porque o TCE-SP publica com atraso: em 06/11/2026 as duas cidades tinham setembro, mas outubro e novembro vinham vazios.
- **Manual:** o disparo aceita os parâmetros `cidades` (uma ou mais; vazio = as já carregadas), `mes_inicial` (AAAA-MM) e `quantidade_de_meses`. As cidades escolhidas são validadas contra `dim_municipio`: só vale cidade que o TCE-SP atende, senão a execução falha logo, com a lista das inválidas. Por exemplo, `["jacarei"]`, `2020-03` e `3` processam março a maio de 2020 de uma cidade só. Dá pra testar sem ativar o DAG: `docker compose --profile airflow exec airflow-scheduler airflow dags test despesas_mensais -c '{"cidades":["jacarei"],"mes_inicial":"2020-03","quantidade_de_meses":3}'`.
- **Histórico:** o *backfill* do Airflow repete o schedule sobre um intervalo de datas (verificado apenas em simulação, com `dry_run`).

**7. Dashboard**

O dashboard é um app Streamlit que lê o mart `fct_despesas_mensais` e as dimensões `dim_estado` e `dim_municipio` (os municípios são identificados pelo código IBGE, e os nomes vêm da dimensão), então o Postgres precisa estar de pé e o `dbt run` já executado. Os filtros, na barra lateral:

- **Estado:** vem das dimensões (`dim_estado`); por enquanto só SP, que é o único estado com município atendido pela fonte.
- **Cidades:** seleção múltipla com os municípios do estado atendidos pelo TCE-SP (`dim_municipio`), abre **sem nenhuma cidade marcada**, em ordem alfabética (sem acento), sem distinção entre as que já têm dado e as que não têm. Escolher uma cidade sem dado no período dispara a carga sob demanda (ver abaixo). Os valores das cidades escolhidas são somados.
- **Período:** calendário de datas, que abre **três meses antes de hoje** (a fonte publica com atraso, então o mês atual estaria vazio) e vai de janeiro de 2014 até hoje. **O dia não é considerado**: a fonte é mensal, então só o mês e o ano contam (15/01 a 10/03 vale janeiro, fevereiro e março inteiros). Isso está dito no formulário, na ajuda do campo e na legenda do resultado ("Período: Janeiro/2020 a Março/2020, meses inteiros"). O Streamlit não tem seletor de só mês e ano; ficou o calendário de datas por enquanto. Janeiro de 2014 é o primeiro mês que a fonte tem em todas as 11 cidades testadas (Jacareí tem todo 2013 vazio); uma cidade que comece depois só terá os meses dela pulados, e a tela diz quais.
- **Confirmar:** cidades e período ficam num formulário: mexer neles não muda a tela, só o botão **Confirmar** aplica. O estado fica fora do formulário (as cidades dependem dele) e o filtro de órgãos vem depois, já sobre o que foi confirmado.

**Carga sob demanda.** Ao confirmar uma cidade e um período sem dado carregado, o dashboard **não grava no banco**: pede ao Airflow, pela API, uma execução do DAG `despesas_mensais` só pra essa cidade e esses meses. A tela mostra o andamento ("na fila", "em andamento"), consulta o Airflow a cada 5 segundos e se atualiza sozinha quando a carga termina. Enquanto a carga está em andamento, o botão **Confirmar fica desabilitado** (pra ninguém disparar pedidos repetidos), e as cidades e o período escolhidos **permanecem** nos filtros depois do resultado. O que isso exige e como se comporta:

- O **Airflow precisa estar no ar** (`--profile airflow`) e o DAG **ativo** (não pausado); senão a tela avisa o que fazer, em vez de enfileirar um pedido que nunca roda.
- O dashboard usa um **usuário restrito do Airflow** (`DASHBOARD_AIRFLOW_USER`, papel `User`: dispara execuções, mas não lê nem altera conexões e variáveis, o que o papel `Op` permitiria), e não o administrador. O `airflow-init` cria o usuário quando `DASHBOARD_AIRFLOW_PASSWORD` está preenchida no `.env`.
- **Limites por pedido**: até 5 cidades e 12 meses; acima disso a tela explica e não dispara nada. Não há teto de data: pedir um mês que a fonte ainda não publicou é permitido, a API responde `[]`, a tarefa fica pulada (código 99) e a tela diz quais cidades e meses ficaram sem dado. Sem os limites, o "Select all" (644 cidades) dispararia milhares de chamadas à API pública.
- **Sem pedidos duplicados**: o pedido tem um identificador determinístico (cidades, mês inicial e quantidade), e o Airflow recusa repetido. Dois cliques, ou duas pessoas pedindo o mesmo, acompanham a mesma execução. Se ela falhou, o botão **Tentar de novo** cria uma nova. Quem não quiser esperar usa **Parar de acompanhar**: a carga continua no Airflow, o botão Confirmar destrava, e **Acompanhar de novo** retoma o acompanhamento.
- Uma cidade carregada uma vez **passa a entrar na atualização mensal** do DAG (que atualiza as cidades já carregadas), sem limite de quantas.
- **Mês que a fonte não tem pra aquela cidade** não é erro: numa execução sob demanda (ou manual) essa combinação é **pulada na hora**, sem esperar e sem derrubar o pedido. As outras combinações seguem, o `dbt run` roda com o que deu certo, e a tela diz exatamente quais meses de quais cidades ficaram sem dado. (Na execução **agendada** continua falhando e tentando de novo no dia seguinte, porque lá o mês costuma só estar atrasado.)
- Se uma etapa **falhar de verdade**, o `dbt run` ainda roda com o que carregou, e a execução termina como falha (a tarefa `conferir` falha de propósito), em vez de parecer sucesso. Um erro real de API pode levar dias pra aparecer como falha por causa das tentativas; o botão **Parar de acompanhar** serve pra isso.
- **Órgãos.**

A tela tem três métricas, um gráfico de evolução mensal (uma linha por etapa do gasto, ou barras lado a lado quando só um mês está selecionado), um gráfico do pago por órgão (a cor indica a cidade) e a tabela de detalhe. Pra carregar mais uma cidade, rode o pipeline ou o DAG pra ela. O dashboard precisa das dimensões prontas: rode `municipios SP`, `municipios-tce-sp` e `dbt run` antes. Os valores de empenhado, liquidado e pago aparecem separados porque são etapas do mesmo gasto e não podem ser somados entre si.

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

## Testes

Dois níveis, que testam coisas diferentes:

```bash
python -m unittest discover -s tests -t . -b    # código Python: 49 testes, sem banco nem rede
cd dbt && dbt test                               # dados: 47 testes, no Postgres
```

Os de Python cobrem as conversões de valor e data, o retry (5xx e corpo inválido tentam de novo, 4xx falha na hora), a regra de "mês sem dado" (pular na carga sob demanda, falhar na agendada), a validação de cidades, a recusa de entradas maliciosas (um slug como `../../x` não chega a chamar a API nem a gravar arquivo), e o cliente do Airflow (pedido com identificador fixo, e o que fazer quando o Airflow recusa um id repetido). Não precisam de nenhuma dependência além das do `requirements.txt`.

## Estrutura

```
src/
  main.py        único ponto de entrada (subcomandos)
  pipeline.py    rodar_pipeline: extract -> load -> transform
  api_client.py  GET com retry e backoff, compartilhado pelas duas APIs
  airflow_client.py  API do Airflow: o dashboard pede cargas sob demanda por aqui
  extract.py     chama a API de despesas e salva o JSON bruto
  municipios.py  carrega os municípios do IBGE e a lista do TCE-SP nas tabelas raw
  load.py        UPSERT do JSON bruto em raw_pagamentos
  transform.py   conversão de tipos e gravação em stg_pagamentos
  backfill.py    carga histórica de um ano inteiro, pras cidades informadas
  db.py          conexão com o Postgres
  validacao.py   valida o que vira URL ou nome de arquivo (cidade, ano, mês, UF)
sql/schema.sql   tabelas raw_pagamentos, raw_ibge_municipios, raw_tce_sp_municipios e stg_pagamentos
sql/migracoes/   migrações pra bancos que já existiam (001: chave do raw_pagamentos passa a ser o código IBGE)
tests/           testes unitários do código Python (unittest, sem banco nem rede)
dbt/
  models/staging/   stg_tce_sp__despesas, stg_ibge__municipios e stg_tce_sp__municipios (views) + sources + testes
  models/marts/     fct_despesas_mensais, dim_estado e dim_municipio (tables) + testes
  tests/            testes singulares (grão único, reconciliações com o staging e o raw, código IBGE x UF, slug único por UF)
airflow/
  Dockerfile        imagem do Airflow + venv isolado com o requirements.txt
  dags/             DAG despesas_mensais
  dbt_profiles/     profile do dbt usado dentro do contêiner (lê variáveis de ambiente)
dashboard/
  app.py            app Streamlit (lê o mart fct_despesas_mensais e as dimensões de localidade)
  Dockerfile        imagem do dashboard (serviço `dashboard` do Compose); roda como usuário comum, não como root
  requirements.txt  dependências do dashboard, separadas das do pipeline
.streamlit/         configuração do Streamlit (sem telemetria, só localhost)
.dockerignore       o que não entra no contexto de build das imagens
.github/dependabot.yml  avisos semanais de versão nova e de correção de segurança nas dependências
SECURITY.md         o que está protegido, o que falta antes de expor ao público e como trocar segredos
docs/notes.md    comportamento da API e particularidades dos dados
data/raw/        JSONs brutos (ignorados pelo git)
```

## Decisões de projeto

- **Raw como JSONB.** A tabela raw guarda o payload exatamente como veio. Campo novo, removido ou com tipo diferente na API não quebra a carga; o problema aparece na camada de transformação, onde os testes do dbt o pegam com mensagem clara.
- **Idempotência.** O load é um UPSERT sobre `UNIQUE (codigo_ibge, periodo)`. O transform apaga e reinsere a partição inteira (município + período, que é uma linha do raw) na mesma transação, porque a API não manda id por despesa. Rodar duas vezes o mesmo período não duplica nada.
- **Retry só onde faz sentido.** Erro 5xx, falha de rede e resposta 200 com corpo que não é JSON são tentados de novo, com espera crescente. Erro 4xx falha na hora, e uma extração que falhou nunca grava arquivo.
- **Um único `main`.** Os módulos só definem funções; só o `main.py` é executável.
- **O município é identificado pelo código IBGE.** O nome se repete entre estados ("Bom Jesus"), então a chave do raw, do staging e do mart é o código de 7 dígitos. O nome que a API do TCE-SP espera (`slug`) fica só nas bordas (linha de comando, parâmetros do DAG, nome do arquivo em `data/raw`) e na `dim_municipio`, que faz a tradução. Quando entrar o primeiro estado novo, o raw e os modelos já estão prontos pra isso; falta só uma fonte de despesas pra ele.
- **dbt.** Staging materializa como view, marts como table. Os testes cobrem `not_null`, `accepted_values` (fornecedor e evento), `relationships` (inclusive despesa → município), e testes singulares: grão do mart, reconciliação com o staging **por município e período** (uma soma geral não pegaria valores trocados entre cidades), código IBGE × UF e slug único por UF.
- **Dois níveis de teste.** O dbt testa os **dados**; o `tests/` testa o **código Python** (conversões, retry, regras de "mês sem dado", validação de cidades, cliente do Airflow).

## Segurança

O projeto foi pensado pra rodar na sua máquina: tudo escuta só em `127.0.0.1`, as senhas são obrigatórias (não há padrão público), o contêiner do dashboard roda sem root, sem capacidades extras e com o sistema de arquivos só de leitura, o dashboard fala com o Airflow por um usuário de papel `User`, e tudo o que vira URL ou nome de arquivo é validado. As dependências estão fixadas e sem vulnerabilidade conhecida. O que ainda falta antes de publicar na internet (usuário do banco só de leitura, SSL, proteção da carga sob demanda) está em [SECURITY.md](SECURITY.md).

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
- [x] Catálogo de municípios (IBGE) e chave do raw pelo código IBGE
- [x] Carga sob demanda pelo dashboard (via API do Airflow)
- [x] Endurecimento de segurança (padrões seguros pra uso local, validação de entrada, usuário do Airflow com o mínimo de permissões; ver [SECURITY.md](SECURITY.md))
- [ ] Publicação na internet (começando pela opção gratuita; checklist no [SECURITY.md](SECURITY.md))
- [ ] Outros estados: o raw e os modelos já estão prontos, mas cada estado precisa de uma fonte de despesas própria (cada tribunal de contas tem uma API diferente, e nenhuma foi verificada)
- [ ] Execução agendada real e backfill do Airflow: só simulados até hoje
- [ ] Seletor de só mês e ano no dashboard (hoje é um calendário de datas em que o dia é ignorado)
