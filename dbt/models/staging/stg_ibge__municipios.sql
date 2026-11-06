-- Uma linha por município, explodida do payload do raw_ibge_municipios.
-- O JSON do IBGE é aninhado: o estado e a região vêm dentro de cada município,
-- por isso o caminho comprido em microrregiao -> mesorregiao -> UF.
with municipios as (
    select
        r.uf as uf_carga,
        m.value as municipio
    from {{ source('raiox', 'raw_ibge_municipios') }} as r,
         jsonb_array_elements(r.payload) as m(value)
)

select
    (municipio ->> 'id')::bigint as codigo_municipio,
    municipio ->> 'nome' as nome_municipio,
    (municipio -> 'microrregiao' -> 'mesorregiao' -> 'UF' ->> 'id')::int as codigo_uf,
    municipio -> 'microrregiao' -> 'mesorregiao' -> 'UF' ->> 'sigla' as uf,
    municipio -> 'microrregiao' -> 'mesorregiao' -> 'UF' ->> 'nome' as nome_uf,
    municipio -> 'microrregiao' -> 'mesorregiao' -> 'UF' -> 'regiao' ->> 'sigla' as sigla_regiao,
    municipio -> 'microrregiao' -> 'mesorregiao' -> 'UF' -> 'regiao' ->> 'nome' as nome_regiao,
    municipio -> 'microrregiao' ->> 'nome' as nome_microrregiao,
    municipio -> 'microrregiao' -> 'mesorregiao' ->> 'nome' as nome_mesorregiao,
    uf_carga
from municipios
