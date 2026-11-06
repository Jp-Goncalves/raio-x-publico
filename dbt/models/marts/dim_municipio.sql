-- Dimensão de municípios. A chave é o código IBGE: o nome se repete entre
-- estados (há vários "Bom Jesus"), então nome sozinho não identifica ninguém.
select
    codigo_municipio,
    nome_municipio,
    uf,
    nome_microrregiao,
    nome_mesorregiao,
    -- Nome sem acento, em minúsculas, com hífen no lugar de espaço e apóstrofo:
    -- "Santa Bárbara d'Oeste" -> "santa-barbara-d-oeste". É o formato que a API
    -- do TCE-SP usa, mas aqui é só um candidato calculado do nome (único dentro
    -- de uma UF, não no país). O vínculo de verdade com a API vem depois.
    trim(both '-' from regexp_replace(
        translate(
            lower(nome_municipio),
            'áàâãäéèêëíìîïóòôõöúùûüçñ',
            'aaaaaeeeeiiiiooooouuuucn'
        ),
        '[^a-z0-9]+', '-', 'g'
    )) as slug_nome
from {{ ref('stg_ibge__municipios') }}
