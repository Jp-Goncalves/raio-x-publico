-- Reconciliação: a dimensão tem exatamente tantos municípios quanto o raw.
-- Falha (devolve uma linha) se alguma etapa perdeu ou duplicou município.
with raw as (
    select sum(jsonb_array_length(payload)) as qtd
    from {{ source('raiox', 'raw_ibge_municipios') }}
),

dim as (
    select count(*) as qtd
    from {{ ref('dim_municipio') }}
)

select
    raw.qtd as qtd_raw,
    dim.qtd as qtd_dim
from raw, dim
where raw.qtd <> dim.qtd
