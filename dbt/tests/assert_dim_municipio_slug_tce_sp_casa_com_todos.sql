-- Falha se algum município da lista do TCE-SP não achou par na dimensão (por
-- exemplo, o IBGE renomeou o município ou o TCE-SP incluiu um novo). Sem este
-- teste, ele sumiria da dimensão em silêncio.
select t.slug
from {{ ref('stg_tce_sp__municipios') }} as t
left join {{ ref('dim_municipio') }} as m on m.slug_tce_sp = t.slug
where m.codigo_municipio is null
