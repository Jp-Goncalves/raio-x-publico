-- Staging: explode o array JSONB do raw em uma linha por despesa, com os
-- tipos corrigidos. Equivalente em SQL ao transform.py, mas roda dentro do
-- Postgres (materializado como VIEW - ver dbt_project.yml).

with despesas as (

    select
        r.id as raw_pagamentos_id,
        r.cidade,
        r.periodo,
        d.value ->> 'orgao'               as orgao,
        d.value ->> 'evento'              as evento,
        d.value ->> 'nr_empenho'          as nr_empenho,
        d.value ->> 'vl_despesa'          as vl_despesa_raw,
        d.value ->> 'dt_emissao_despesa'  as dt_emissao_despesa_raw,
        d.value ->> 'id_fornecedor'       as id_fornecedor_raw,
        d.value ->> 'nm_fornecedor'       as nm_fornecedor
    from {{ source('raiox', 'raw_pagamentos') }} as r,
         jsonb_array_elements(r.payload) as d(value)

),

fornecedor_partes as (

    select
        *,
        -- "CNPJ - PESSOA JURÍDICA - 123..." -> {CNPJ, PESSOA JURÍDICA, 123...}
        -- "PESSOA FÍSICA - 921998"          -> {PESSOA FÍSICA, 921998}
        -- número de partes varia; tipo é sempre o 1º, documento o último
        string_to_array(id_fornecedor_raw, ' - ') as partes
    from despesas

)

select
    raw_pagamentos_id,
    cidade,
    periodo,
    orgao,
    evento,
    nr_empenho,
    -- BR: ponto é milhar, vírgula é decimal
    replace(replace(vl_despesa_raw, '.', ''), ',', '.')::numeric(14, 2) as vl_despesa,
    to_date(dt_emissao_despesa_raw, 'DD/MM/YYYY')                      as dt_emissao_despesa,
    partes[1]                                                          as tipo_identificacao_fornecedor,
    partes[array_length(partes, 1)]                                    as numero_documento_fornecedor,
    nm_fornecedor
from fornecedor_partes
