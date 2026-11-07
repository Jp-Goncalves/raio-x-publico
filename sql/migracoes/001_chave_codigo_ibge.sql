-- Migração 001: a chave de raw_pagamentos passa de `cidade` (slug) para `codigo_ibge`.
--
-- Pra quê: o nome se repete entre estados ("Bom Jesus"); o código IBGE não. Instalações
-- NOVAS já nascem assim pelo sql/schema.sql: este arquivo é só pra um banco que já existia.
--
-- Pré-requisito: dim_municipio construída (python src/main.py municipios SP,
-- python src/main.py municipios-tce-sp e dbt run), porque o código vem dela.
--
-- Como rodar (uma vez, é seguro repetir):
--   docker exec -i raio-x-publico-db psql -U raiox -d raiox_publico -v ON_ERROR_STOP=1 \
--       < sql/migracoes/001_chave_codigo_ibge.sql
-- Depois, rode `dbt run` pra recriar a view de staging.
--
-- Tudo numa transação: se qualquer passo falhar, nada muda.
BEGIN;

-- cópia de segurança, só da primeira vez; apague quando conferir (DROP TABLE raw_pagamentos_bkp_pre_ibge)
CREATE TABLE IF NOT EXISTS raw_pagamentos_bkp_pre_ibge AS TABLE raw_pagamentos;

-- 1) raw_pagamentos: acrescenta o código e preenche a partir do nome. O slug é único dentro de
--    uma UF; todos os dados existentes são de SP.
ALTER TABLE raw_pagamentos ADD COLUMN IF NOT EXISTS codigo_ibge BIGINT;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'raw_pagamentos' AND column_name = 'cidade') THEN
        UPDATE raw_pagamentos r
           SET codigo_ibge = m.codigo_municipio
          FROM dim_municipio m
         WHERE r.codigo_ibge IS NULL
           AND m.uf = 'SP'
           AND m.slug_nome = r.cidade;
    END IF;
END $$;

-- 2) nenhuma linha pode ficar sem código: aborta (e desfaz tudo) se alguma ficar
DO $$
DECLARE
    sem_codigo INTEGER;
BEGIN
    SELECT count(*) INTO sem_codigo FROM raw_pagamentos WHERE codigo_ibge IS NULL;
    IF sem_codigo > 0 THEN
        RAISE EXCEPTION 'migração abortada: % linha(s) de raw_pagamentos sem código IBGE (a dim_municipio está construída?)', sem_codigo;
    END IF;
END $$;

-- 3) stg_pagamentos (versão em Python): o código vem da própria linha do raw a que ela aponta
ALTER TABLE stg_pagamentos ADD COLUMN IF NOT EXISTS codigo_ibge BIGINT;
UPDATE stg_pagamentos s
   SET codigo_ibge = r.codigo_ibge
  FROM raw_pagamentos r
 WHERE r.id = s.raw_pagamentos_id
   AND s.codigo_ibge IS NULL;

-- 4) troca de chave e remoção da coluna antiga. A view do dbt depende de raw_pagamentos.cidade,
--    então sai antes (o `dbt run` a recria).
--    (só enquanto a coluna antiga existe: repetir a migração depois do dbt run não apaga a view nova)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'raw_pagamentos' AND column_name = 'cidade') THEN
        DROP VIEW IF EXISTS stg_tce_sp__despesas;
    END IF;
END $$;

ALTER TABLE raw_pagamentos ALTER COLUMN codigo_ibge SET NOT NULL;
DROP INDEX IF EXISTS uq_raw_pagamentos_cidade_periodo;
CREATE UNIQUE INDEX IF NOT EXISTS uq_raw_pagamentos_codigo_periodo
    ON raw_pagamentos (codigo_ibge, periodo);
ALTER TABLE raw_pagamentos DROP COLUMN IF EXISTS cidade;

ALTER TABLE stg_pagamentos ALTER COLUMN codigo_ibge SET NOT NULL;
DROP INDEX IF EXISTS idx_stg_pagamentos_cidade_periodo;
ALTER TABLE stg_pagamentos DROP COLUMN IF EXISTS cidade;
CREATE INDEX IF NOT EXISTS idx_stg_pagamentos_raw_id ON stg_pagamentos (raw_pagamentos_id);
CREATE INDEX IF NOT EXISTS idx_stg_pagamentos_codigo_periodo ON stg_pagamentos (codigo_ibge, periodo);

COMMIT;
