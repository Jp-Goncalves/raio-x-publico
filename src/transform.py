from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from db import conectar
from municipios import codigo_ibge_da_cidade


def ler_raw(cidade: str, ano: int, mes: int) -> tuple[int, int, list]:
    periodo = f"{ano:04d}-{mes:02d}"
    codigo_ibge = codigo_ibge_da_cidade(cidade)
    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, payload FROM raw_pagamentos WHERE codigo_ibge = %s AND periodo = %s;",
                (codigo_ibge, periodo),
            )
            row = cur.fetchone()

    if row is None:
        raise ValueError(f"nenhum raw encontrado para {cidade}/{periodo} - rode o load primeiro")

    raw_id, payload = row
    return raw_id, codigo_ibge, payload


def converter_valor(valor: str) -> Decimal:
    # BR: ponto é milhar, vírgula é decimal -> tira ponto, troca vírgula por ponto
    limpo = valor.replace(".", "").replace(",", ".")
    return Decimal(limpo)


def converter_data(valor: str) -> date:
    return datetime.strptime(valor, "%d/%m/%Y").date()


def separar_fornecedor(valor: str) -> tuple[str, str]:
    # "CNPJ - PESSOA JURÍDICA - 65069593000198" -> ("CNPJ", "65069593000198")
    # "INSCRIÇÃO GENÉRICA-OUTROS - PF0339046"   -> ("INSCRIÇÃO GENÉRICA-OUTROS", "PF0339046")
    # número de partes varia, mas o tipo sempre é o primeiro e o documento o último
    partes = valor.split(" - ")
    return partes[0], partes[-1]


def transformar(dados: list) -> tuple[list, list]:
    transformados = []
    erros = []

    for i, registro in enumerate(dados):
        try:
            tipo_doc, numero_doc = separar_fornecedor(registro["id_fornecedor"])
            transformados.append({
                "orgao": registro["orgao"],
                "evento": registro["evento"],
                "nr_empenho": registro["nr_empenho"],
                "vl_despesa": converter_valor(registro["vl_despesa"]),
                "dt_emissao_despesa": converter_data(registro["dt_emissao_despesa"]),
                "tipo_identificacao_fornecedor": tipo_doc,
                "numero_documento_fornecedor": numero_doc,
                "nm_fornecedor": registro["nm_fornecedor"],
            })
        except (InvalidOperation, ValueError) as e:
            erros.append((i, registro, str(e)))

    return transformados, erros


def gravar_stg(raw_id: int, codigo_ibge: int, periodo: str, transformados: list) -> None:
    linhas = [
        (
            raw_id,
            codigo_ibge,
            periodo,
            r["orgao"],
            r["evento"],
            r["nr_empenho"],
            r["vl_despesa"],
            r["dt_emissao_despesa"],
            r["tipo_identificacao_fornecedor"],
            r["numero_documento_fornecedor"],
            r["nm_fornecedor"],
        )
        for r in transformados
    ]

    # DELETE + INSERT na mesma transação (o "with conectar()" só commita no
    # final, sem erro) = partition overwrite atômico: ou a partição inteira
    # é trocada, ou nada muda.
    with conectar() as conn:
        with conn.cursor() as cur:
            # a partição (município + período) é exatamente uma linha do raw
            cur.execute("DELETE FROM stg_pagamentos WHERE raw_pagamentos_id = %s;", (raw_id,))
            cur.executemany(
                """
                INSERT INTO stg_pagamentos (
                    raw_pagamentos_id, codigo_ibge, periodo, orgao, evento, nr_empenho,
                    vl_despesa, dt_emissao_despesa, tipo_identificacao_fornecedor,
                    numero_documento_fornecedor, nm_fornecedor
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """,
                linhas,
            )

    print(f"{len(linhas)} linhas gravadas em stg_pagamentos para o município {codigo_ibge}/{periodo}")


def transformar_e_gravar(cidade: str, ano: int, mes: int) -> None:
    periodo = f"{ano:04d}-{mes:02d}"
    raw_id, codigo_ibge, dados = ler_raw(cidade, ano, mes)
    transformados, erros = transformar(dados)

    print(f"{len(dados)} registros lidos")
    print(f"{len(transformados)} transformados com sucesso")
    print(f"{len(erros)} com erro")

    if erros:
        print("\nPrimeiros erros:")
        for i, registro, msg in erros[:5]:
            print(f"  linha {i}: {msg} -> {registro}")
        raise ValueError(f"{len(erros)} registro(s) falharam na conversão - partição não gravada")

    gravar_stg(raw_id, codigo_ibge, periodo, transformados)
