-- Tabela raw: guarda o JSON bruto da API como veio, sem tratamento.
-- JSONB em vez de colunas por campo porque o formato pode mudar (campo
-- novo/removido/tipo diferente) sem quebrar a carga - o parsing definitivo
-- fica pra camada de transform/dbt.
CREATE TABLE IF NOT EXISTS raw_pagamentos (
    id SERIAL PRIMARY KEY,
    cidade TEXT NOT NULL,
    periodo TEXT NOT NULL, -- formato AAAA-MM, ex.: '2020-01'
    payload JSONB NOT NULL,
    extracted_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- UNIQUE (não só índice) porque o load é um UPSERT: reprocessar o mesmo
-- cidade+periodo (rerun de falha, backfill) precisa substituir, não duplicar.
CREATE UNIQUE INDEX IF NOT EXISTS uq_raw_pagamentos_cidade_periodo
    ON raw_pagamentos (cidade, periodo);

-- Tabela staging: uma linha por despesa (o raw explode o array em linhas),
-- já com os tipos corrigidos. Sem UNIQUE por linha porque a API não manda
-- nenhum id de despesa - a idempotência aqui é por partição inteira
-- (cidade+periodo), não por linha: transform.py apaga e recarrega a
-- partição inteira a cada rodada (partition overwrite), nunca UPSERT linha
-- a linha.
CREATE TABLE IF NOT EXISTS stg_pagamentos (
    id SERIAL PRIMARY KEY,
    raw_pagamentos_id INTEGER NOT NULL REFERENCES raw_pagamentos (id),
    cidade TEXT NOT NULL,
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

-- Não-único: acelera o DELETE por partição e as consultas por cidade/período.
CREATE INDEX IF NOT EXISTS idx_stg_pagamentos_cidade_periodo
    ON stg_pagamentos (cidade, periodo);
