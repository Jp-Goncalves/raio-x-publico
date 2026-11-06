-- Mart: uma linha por cidade x mês x órgão, com as três etapas do gasto
-- público lado a lado (empenho -> liquidação -> pagamento).
--
-- Cada etapa vira uma coluna própria porque somar vl_despesa direto, sem
-- olhar o evento, conta o mesmo gasto várias vezes (empenhado + liquidado +
-- pago do MESMO compromisso). Aqui nenhuma coluna mistura etapas.
--
-- empenhado_liquido = Empenhado + Reforço - Anulação (pode ficar negativo num
-- mês em que o órgão anula empenhos de meses anteriores).

select
    cidade,
    periodo,
    orgao,

    sum(case evento
            when 'Empenhado' then vl_despesa
            when 'Reforço'   then vl_despesa
            when 'Anulação'  then -vl_despesa
            else 0
        end) as empenhado_liquido,

    sum(case when evento = 'Valor Liquidado' then vl_despesa else 0 end) as liquidado,
    sum(case when evento = 'Valor Pago'      then vl_despesa else 0 end) as pago,

    count(*) as qtd_lancamentos

from {{ ref('stg_tce_sp__despesas') }}
group by cidade, periodo, orgao
