-- Uma linha por município que o TCE-SP atende, explodida do payload do raw.
select
    m.value ->> 'municipio' as slug,
    m.value ->> 'municipio_extenso' as nome_extenso
from {{ source('raiox', 'raw_tce_sp_municipios') }} as r,
     jsonb_array_elements(r.payload) as m(value)
