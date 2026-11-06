-- Falha se os 2 primeiros dígitos do código IBGE do município não forem o
-- código da UF dele (ex.: 3524402 Jacareí -> 35 = SP), ou se a UF lida de
-- dentro do município for diferente da chave com que o raw foi carregado.
select
    m.codigo_municipio,
    m.uf,
    e.codigo_uf
from {{ ref('dim_municipio') }} as m
join {{ ref('dim_estado') }} as e on e.uf = m.uf
where m.codigo_municipio / 100000 <> e.codigo_uf

union all

select
    codigo_municipio,
    uf,
    codigo_uf
from {{ ref('stg_ibge__municipios') }}
where uf <> uf_carga
