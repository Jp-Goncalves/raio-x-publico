-- Tabela raw: guarda o JSON bruto da API como veio, sem tratamento.
-- JSONB em vez de colunas por campo porque o formato pode mudar (campo
-- novo/removido/tipo diferente) sem quebrar a carga - o parsing definitivo
-- fica pra camada de transform/dbt.
--
-- A chave do município é o CÓDIGO IBGE (7 dígitos), não o nome: o nome se repete entre
-- estados (há vários "Bom Jesus"). O nome que a API do TCE-SP espera (slug, ex.: 'jacarei')
-- continua existindo, mas só nas bordas (CLI, DAG, nome do arquivo em data/raw) e na
-- dimensão dim_municipio; o load traduz slug -> código.
CREATE TABLE IF NOT EXISTS raw_pagamentos (
    id SERIAL PRIMARY KEY,
    codigo_ibge BIGINT NOT NULL,
    periodo TEXT NOT NULL, -- formato AAAA-MM, ex.: '2020-01'
    payload JSONB NOT NULL,
    extracted_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- UNIQUE (não só índice) porque o load é um UPSERT: reprocessar o mesmo
-- município+periodo (rerun de falha, backfill) precisa substituir, não duplicar.
CREATE UNIQUE INDEX IF NOT EXISTS uq_raw_pagamentos_codigo_periodo
    ON raw_pagamentos (codigo_ibge, periodo);

-- Tabela raw dos municípios (API de localidades do IBGE): uma linha por UF, com a
-- lista inteira de municípios da UF em JSONB. Adicionar outro estado é só mais uma
-- linha, sem mudar a tabela. O UPSERT por uf torna a recarga idempotente.
CREATE TABLE IF NOT EXISTS raw_ibge_municipios (
    uf TEXT PRIMARY KEY CHECK (uf ~ '^[A-Z]{2}$'), -- sigla, ex.: 'SP'
    payload JSONB NOT NULL,
    extracted_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Lista de municípios que o TCE-SP atende (endpoint /municipios da API de
-- transparência): [{"municipio": "jacarei", "municipio_extenso": "Jacareí"}, ...].
-- Uma linha só (id fixo em 1): é uma lista única, recarregada por inteiro.
-- Serve pra ligar o município do IBGE ao nome que a API de despesas espera.
CREATE TABLE IF NOT EXISTS raw_tce_sp_municipios (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    payload JSONB NOT NULL,
    extracted_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Tabela staging: uma linha por despesa (o raw explode o array em linhas),
-- já com os tipos corrigidos. Sem UNIQUE por linha porque a API não manda
-- nenhum id de despesa - a idempotência aqui é por partição inteira
-- (município+periodo, que é uma linha do raw), não por linha: transform.py
-- apaga e recarrega a partição inteira a cada rodada (partition overwrite),
-- nunca UPSERT linha a linha.
CREATE TABLE IF NOT EXISTS stg_pagamentos (
    id SERIAL PRIMARY KEY,
    raw_pagamentos_id INTEGER NOT NULL REFERENCES raw_pagamentos (id),
    codigo_ibge BIGINT NOT NULL,
    periodo TEXT NOT NULL,
    orgao TEXT NOT NULL,
    evento TEXT NOT NULL,
    nr_empenho TEXT NOT NULL,
    vl_despesa NUMERIC(14, 2) NOT NULL,
    dt_emissao_despesa DATE NOT NULL,
    tipo_identificacao_fornecedor TEXT NOT NULL, -- ex.: CNPJ, PESSOA FÍSICA, IDENTIFICAÇÃO ESPECIAL, INSCRIÇÃO GENÉRICA-OUTROS - nem sempre é um "documento" de fato
    numero_documento_fornecedor TEXT NOT NULL,
    nm_fornecedor TEXT NOT NULL,
    transformed_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Não-único: acelera o DELETE por partição (uma linha do raw) e as consultas por município.
CREATE INDEX IF NOT EXISTS idx_stg_pagamentos_raw_id
    ON stg_pagamentos (raw_pagamentos_id);
CREATE INDEX IF NOT EXISTS idx_stg_pagamentos_codigo_periodo
    ON stg_pagamentos (codigo_ibge, periodo);
