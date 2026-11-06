-- Todo município de SP deve ter par na lista do TCE-SP, com uma exceção
-- conhecida: a capital (código IBGE 3550308), auditada pelo TCM-SP. Se outro
-- município paulista aparecer sem par, algo mudou na fonte ou no nome.
select
    codigo_municipio,
    nome_municipio
from {{ ref('dim_municipio') }}
where uf = 'SP'
  and slug_tce_sp is null
  and codigo_municipio <> 3550308
