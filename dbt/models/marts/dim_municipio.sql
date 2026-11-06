-- Dimensão de municípios. A chave é o código IBGE: o nome se repete entre
-- estados (há vários "Bom Jesus"), então nome sozinho não identifica ninguém.
select
    m.codigo_municipio,
    m.nome_municipio,
    m.uf,
    m.nome_microrregiao,
    m.nome_mesorregiao,
    -- Nome sem acento, em minúsculas, com hífen no lugar de espaço e apóstrofo:
    -- "Santa Bárbara d'Oeste" -> "santa-barbara-d-oeste". Único dentro de uma
    -- UF, não no país.
    m.slug_nome,
    -- Nome que a API de despesas do TCE-SP espera. Vazio = o TCE-SP não atende
    -- esse município (outros estados, ou a capital paulista, que é do TCM-SP).
    t.slug as slug_tce_sp
from (
    select
        codigo_municipio,
        nome_municipio,
        uf,
        nome_microrregiao,
        nome_mesorregiao,
        trim(both '-' from regexp_replace(
            translate(
                lower(nome_municipio),
                'áàâãäéèêëíìîïóòôõöúùûüçñ',
                'aaaaaeeeeiiiiooooouuuucn'
            ),
            '[^a-z0-9]+', '-', 'g'
        )) as slug_nome
    from {{ ref('stg_ibge__municipios') }}
) as m
-- o TCE-SP só atende SP: sem o filtro de UF, o "bom-jesus" de outro estado
-- casaria com o de SP só porque o nome é igual
left join {{ ref('stg_tce_sp__municipios') }} as t
    on m.uf = 'SP'
    and t.slug = m.slug_nome
