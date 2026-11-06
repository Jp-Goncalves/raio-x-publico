-- Teste singular: o grão do mart é cidade + período + órgão, então nenhuma
-- combinação pode aparecer duas vezes. O teste devolve as combinações
-- duplicadas; zero linhas = passa.

select
    cidade,
    periodo,
    orgao,
    count(*) as n
from {{ ref('fct_despesas_mensais') }}
group by cidade, periodo, orgao
having count(*) > 1
