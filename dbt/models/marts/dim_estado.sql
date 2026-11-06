-- Dimensão de estados. O IBGE não manda uma lista de estados junto com os
-- municípios: o estado vem repetido dentro de cada um. Por isso o DISTINCT.
select distinct
    codigo_uf,
    uf,
    nome_uf,
    sigla_regiao,
    nome_regiao
from {{ ref('stg_ibge__municipios') }}
