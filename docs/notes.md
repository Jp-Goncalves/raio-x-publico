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
