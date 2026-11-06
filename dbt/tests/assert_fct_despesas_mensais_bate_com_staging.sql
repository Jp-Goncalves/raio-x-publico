-- Teste singular de reconciliação: o total de cada coluna do mart tem que
-- ser igual ao total calculado direto do staging. Se a agregação perdesse ou
-- duplicasse algum valor, as somas divergiriam. Devolve linha só se divergir.

with mart as (

    select
        sum(empenhado_liquido) as empenhado_liquido,
        sum(liquidado)         as liquidado,
        sum(pago)              as pago
    from {{ ref('fct_despesas_mensais') }}

),

staging as (

    select
        sum(case evento
                when 'Empenhado' then vl_despesa
                when 'Reforço'   then vl_despesa
                when 'Anulação'  then -vl_despesa
                else 0
            end) as empenhado_liquido,
        sum(case when evento = 'Valor Liquidado' then vl_despesa else 0 end) as liquidado,
        sum(case when evento = 'Valor Pago'      then vl_despesa else 0 end) as pago
    from {{ ref('stg_tce_sp__despesas') }}

)

select
    mart.empenhado_liquido as mart_empenhado_liquido,
    staging.empenhado_liquido as staging_empenhado_liquido,
    mart.liquidado as mart_liquidado,
    staging.liquidado as staging_liquidado,
    mart.pago as mart_pago,
    staging.pago as staging_pago
from mart
cross join staging
where mart.empenhado_liquido <> staging.empenhado_liquido
   or mart.liquidado <> staging.liquidado
   or mart.pago <> staging.pago
