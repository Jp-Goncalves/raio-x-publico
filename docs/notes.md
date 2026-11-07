# API - TCE-SP Transparência

Endpoint: `https://transparencia.tce.sp.gov.br/api/json/despesas/{cidade}/{ano}/{mes}`

Exemplo: `https://transparencia.tce.sp.gov.br/api/json/despesas/jacarei/2020/1`

- `cidade`: nome da cidade em minúsculas, sem acento (ex.: `jacarei`)
- `ano`: AAAA
- `mes`: número do mês sem zero à esquerda (ex.: `1` para janeiro)

## Formato da resposta

Array plano de objetos, sem metadados de paginação (retorna tudo de uma vez):

```json
[
  {
    "orgao": "CÂMARA MUNICIPAL DE JACAREI",
    "mes": "Janeiro",
    "evento": "Empenhado",
    "nr_empenho": "114-2020",
    "id_fornecedor": "CNPJ - PESSOA JURÍDICA - 65069593000198",
    "nm_fornecedor": "TANBY COMÉRCIO DE PAPÉIS LTDA",
    "dt_emissao_despesa": "30/01/2020",
    "vl_despesa": "1266,00"
  }
]
```

## Observações

- Todos os campos vêm como string, mesmo os numéricos.
- `vl_despesa`: decimal com vírgula (formato BR) - precisa `replace(',', '.')` antes de converter pra numeric.
- `dt_emissao_despesa`: formato `DD/MM/AAAA`.
- `id_fornecedor` mistura tipo + documento no mesmo campo (`"CNPJ - PESSOA JURÍDICA - 65069593000198"` ou `"CPF - PESSOA FÍSICA - ..."`) - vai precisar parsing/split na camada de transform.
- Sem autenticação necessária pra essa chamada de teste.

## Paginação / truncamento (validado)

Testado com Campinas (cidade grande) em 2020/1: retornou **6566 registros em uma
única resposta**, ~1.9MB, JSON válido e completo (parseado com sucesso, sem
truncamento). Confirma que a API não pagina - devolve o período inteiro de uma vez.
`extract.py` não precisa de lógica de paginação, mas deve tratar respostas grandes
(streaming/timeout de request pra cidades grandes, se necessário).

Encoding: JSON vem em UTF-8 limpo (acentos como `\uXXXX` ou UTF-8 direto,
decodificam certinho). Não há corrupção de dados - se aparecer caractere estranho,
é exibição do terminal/console, não o dado em si.

## Cidades fora da jurisdição do TCE-SP

`sao-paulo` e `saopaulo` retornam array vazio `[]` (não erro) - a capital é
auditada pelo TCM-SP (Tribunal de Contas do Município), não pelo TCE-SP. Array
vazio pode significar "cidade fora da base" ou "sem despesas no período" -
`extract.py`/`load.py` não devem tratar isso como erro, mas vale logar pra
diferenciar os dois casos manualmente se necessário.

## Campo `evento`: etapas do mesmo gasto

O campo `evento` tem 5 valores, e eles **não são gastos distintos**: são etapas do
ciclo da despesa pública (empenho, liquidação, pagamento) mais dois ajustes de
empenho. Medido em Jacareí + Campinas, 2020 inteiro:

| evento | linhas | total (R$ mi) |
|---|---|---|
| Empenhado | 42201 | 8462,4 |
| Valor Liquidado | 64393 | 6440,4 |
| Valor Pago | 76560 | 6200,9 |
| Anulação | 8825 | 2177,1 |
| Reforço | 1930 | 395,6 |

- Empenho líquido = Empenhado + Reforço − Anulação = R$ 6.680,9 mi.
- Os totais seguem a ordem esperada: empenho líquido > liquidado > pago.
- Somar `vl_despesa` sem separar o evento dá R$ 23,7 bi, número enganoso, porque conta
  o mesmo gasto em várias etapas.
- Interpretação de `Reforço` e `Anulação` como ajustes de empenho vem do conhecimento
  da contabilidade pública, não de documentação da API. Os totais batem com ela, mas
  vale confirmar com a fonte.
- Num mês, o empenho líquido de um órgão pode ser negativo (anulação de empenhos de
  meses anteriores) e o pago pode superar o liquidado (pagamento de liquidações
  antigas). Ambos são dado legítimo.

## Campo `id_fornecedor`: 4 categorias

Depois do split por `" - "`, a primeira parte (`tipo_identificacao_fornecedor`) tem
4 valores: `CNPJ`, `PESSOA FÍSICA`, `IDENTIFICAÇÃO ESPECIAL` e
`INSCRIÇÃO GENÉRICA-OUTROS`. Só `CNPJ` é de fato um tipo de documento; as outras
categorias vêm sem CPF/CNPJ explícito. O formato varia entre 2 e 3 partes
(`"CNPJ - PESSOA JURÍDICA - 65069593000198"` contra `"PESSOA FÍSICA - 921998"`), então
o tipo é sempre a primeira parte e o documento a última. Os 4 valores são validados por
um teste `accepted_values` do dbt.

## Mês sem dado: a API responde `200` com `[]`, nunca erro

Para mês não publicado, cidade fora da jurisdição ou ano sem dado (testado com 1900 e
2100), a resposta é `200` com `[]`. Não há como provocar um erro real da API por parâmetro.
Por isso "a fonte não tem esse mês" e "a fonte caiu" são casos diferentes no pipeline: o
primeiro vira tarefa pulada (execução manual/sob demanda) ou falha com nova tentativa
(execução agendada); o segundo é um erro HTTP ou de rede, com retry.

## Defasagem de publicação

Medido em 06/11/2026, em Jacareí e Campinas: julho, agosto e setembro de 2026 tinham dado;
outubro e novembro vinham vazios. Só dois pontos de medida: não se sabe em que dia do mês os
dados costumam sair. O DAG usa três meses de defasagem (`MESES_DE_DEFASAGEM`) por margem.

## Início da série: janeiro de 2014

Em Jacareí, os 12 meses de 2013 vêm vazios e 2014-01 tem dado (4.849 registros). Em outras
10 cidades (Campinas, São José dos Campos, Santos, Ribeirão Preto, Taubaté, Lorena, Amparo,
Aguaí, Barra do Turvo e Américo de Campos), dezembro de 2013 vem vazio e janeiro de 2014 tem
dado. Não há documentação confirmando 2014 como início, e uma cidade pode ter começado depois:
nesse caso os meses dela só voltam vazios.

## Campo `dt_emissao_despesa`: data do lançamento, nem sempre no mês consultado

É a data do **próprio lançamento** (empenho, liquidação, pagamento), não a do empenho
original: comparando o mesmo empenho, 92% dos pagamentos e 68% das liquidações têm data
posterior à do empenho. Medido em Jacareí, Campinas e as demais cidades carregadas
(267.075 linhas no momento da medição):

| evento | dentro do mês consultado | em mês anterior |
|---|---|---|
| Empenhado, Reforço, Anulação | 100% | 0% |
| Valor Pago | 99,1% | 0,8% |
| Valor Liquidado | 87,9% | 12,1% |

- Parte das liquidações aparece no relatório de um mês com data de meses antes (até 11 meses
  ou mais). Há também 24 linhas com data no mês **seguinte** ao consultado (esquisitice da
  fonte).
- Consequência: o total "por data de emissão" de um mês **não é igual** ao total "por mês do
  relatório" (que é o que o mart `fct_despesas_mensais` e a API usam). Para um filtro por dia
  ficar correto, seria preciso carregar também os meses seguintes, porque lançamentos datados
  de um mês podem vir no relatório dos meses seguintes. Sem isso, o último mês carregado
  ficaria incompleto sem aviso.
- Decisão: o dashboard fica no critério mensal (mês do relatório); o dia escolhido no
  calendário é ignorado. Um filtro por dia seria uma visão à parte, "por data de emissão",
  com um mart diário (4.439 linhas contra 218 do mensal, com os dados de hoje) e um teste que
  confira que a soma dos dias agrupada pelo mês do relatório bate com o mensal.

## Endpoint de municípios

`https://transparencia.tce.sp.gov.br/api/json/municipios` devolve `{"municipio": "jacarei",
"municipio_extenso": "Jacareí"}` para 644 municípios, os mesmos 645 do IBGE menos a capital
(TCM-SP). O `slug` (`municipio`) é o nome do IBGE sem acento, em minúsculas, com hífen no
lugar de espaço e apóstrofo: a regra reproduzida em SQL em `dim_municipio.slug_nome` bate
com os 644 slugs. Nomes se repetem entre estados (há vários "Bom Jesus"), então a chave de
um município é o código IBGE, e o slug só vale dentro de SP.
