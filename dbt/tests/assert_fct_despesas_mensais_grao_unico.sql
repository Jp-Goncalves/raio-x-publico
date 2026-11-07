-- Teste singular: o grão do mart é município + período + órgão, então nenhuma
-- combinação pode aparecer duas vezes. O teste devolve as combinações
-- duplicadas; zero linhas = passa.

select
    codigo_municipio,
    periodo,
    orgao,
    count(*) as n
from {{ ref('fct_despesas_mensais') }}
group by codigo_municipio, periodo, orgao
having count(*) > 1
