-- Falha se dois municípios da mesma UF tiverem o mesmo slug_nome.
-- (Entre UFs diferentes pode repetir: há "Bom Jesus" em vários estados.)
select
    uf,
    slug_nome,
    count(*) as qtd
from {{ ref('dim_municipio') }}
group by uf, slug_nome
having count(*) > 1
