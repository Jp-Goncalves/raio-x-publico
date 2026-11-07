-- Teste singular de reconciliação: para cada município e período, o total de cada coluna do
-- mart tem que ser igual ao total calculado direto do staging. Se a agregação perdesse,
-- duplicasse ou trocasse algum valor (inclusive entre municípios, que uma soma geral não
-- pegaria), as somas divergiriam. Devolve linha só se divergir.

with mart as (

    select
        codigo_municipio,
        periodo,
        sum(empenhado_liquido) as empenhado_liquido,
        sum(liquidado)         as liquidado,
        sum(pago)              as pago
    from {{ ref('fct_despesas_mensais') }}
    group by codigo_municipio, periodo

),

staging as (

    select
        codigo_municipio,
        periodo,
        sum(case evento
                when 'Empenhado' then vl_despesa
                when 'Reforço'   then vl_despesa
                when 'Anulação'  then -vl_despesa
                else 0
            end) as empenhado_liquido,
        sum(case when evento = 'Valor Liquidado' then vl_despesa else 0 end) as liquidado,
        sum(case when evento = 'Valor Pago'      then vl_despesa else 0 end) as pago
    from {{ ref('stg_tce_sp__despesas') }}
    group by codigo_municipio, periodo

)

-- full join: um município/período que existe só de um lado também é divergência
select
    coalesce(mart.codigo_municipio, staging.codigo_municipio) as codigo_municipio,
    coalesce(mart.periodo, staging.periodo) as periodo,
    mart.empenhado_liquido as mart_empenhado_liquido,
    staging.empenhado_liquido as staging_empenhado_liquido,
    mart.liquidado as mart_liquidado,
    staging.liquidado as staging_liquidado,
    mart.pago as mart_pago,
    staging.pago as staging_pago
from mart
full join staging
    on mart.codigo_municipio = staging.codigo_municipio
    and mart.periodo = staging.periodo
where mart.empenhado_liquido is distinct from staging.empenhado_liquido
   or mart.liquidado is distinct from staging.liquidado
   or mart.pago is distinct from staging.pago
