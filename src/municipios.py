import psycopg
from psycopg.types.json import Jsonb

from api_client import get_json
from db import conectar

IBGE_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios"
TCE_SP_MUNICIPIOS_URL = "https://transparencia.tce.sp.gov.br/api/json/municipios"


def _uf_do_payload(dados: list) -> str:
    # a sigla vem dentro de cada município (microrregiao.mesorregiao.UF.sigla). Usamos ela como
    # chave, e não o que foi digitado: o IBGE aceita 'sp' e até o código '35' no lugar da sigla.
    siglas = {m["microrregiao"]["mesorregiao"]["UF"]["sigla"] for m in dados}
    if len(siglas) != 1:
        raise ValueError(f"esperava municípios de uma única UF, vieram: {sorted(siglas)}")
    return siglas.pop()


def carregar_municipios(uf: str) -> str:
    dados = get_json(IBGE_URL.format(uf=uf), f"IBGE municípios {uf}")

    if not dados:
        # UF inexistente devolve 200 com lista vazia. Nada é gravado: um [] não pode
        # sobrescrever (via UPSERT) um raw bom.
        raise ValueError(f"o IBGE não devolveu municípios para a UF '{uf}': ela existe?")

    sigla = _uf_do_payload(dados)

    with conectar() as conn:
        conn.execute(
            """
            INSERT INTO raw_ibge_municipios (uf, payload)
            VALUES (%s, %s)
            ON CONFLICT (uf) DO UPDATE
                SET payload = EXCLUDED.payload,
                    extracted_at = NOW();
            """,
            (sigla, Jsonb(dados)),
        )

    print(f"{len(dados)} municípios carregados para {sigla}")
    return sigla


def carregar_municipios_tce_sp() -> int:
    dados = get_json(TCE_SP_MUNICIPIOS_URL, "TCE-SP municípios")

    # lista vazia ou sem o campo que o dbt vai ler: não grava, pra não trocar um raw bom por lixo
    if not dados or not all(isinstance(m, dict) and m.get("municipio") for m in dados):
        raise ValueError("lista de municípios do TCE-SP vazia ou fora do formato esperado")

    with conectar() as conn:
        conn.execute(
            """
            INSERT INTO raw_tce_sp_municipios (id, payload)
            VALUES (1, %s)
            ON CONFLICT (id) DO UPDATE
                SET payload = EXCLUDED.payload,
                    extracted_at = NOW();
            """,
            (Jsonb(dados),),
        )

    print(f"{len(dados)} municípios do TCE-SP carregados")
    return len(dados)


def codigo_ibge_da_cidade(cidade: str) -> int:
    """Traduz o nome que a API do TCE-SP espera (slug, ex.: 'jacarei') no código IBGE.

    O raw é identificado pelo código, não pelo nome (o nome se repete entre estados), mas CLI,
    DAG e nome de arquivo continuam usando o slug. A tradução vem da dim_municipio.
    """
    try:
        with conectar() as conn:
            linha = conn.execute(
                "SELECT codigo_municipio FROM dim_municipio WHERE slug_tce_sp = %s", (cidade,)
            ).fetchone()
    except psycopg.errors.UndefinedTable as e:
        raise ValueError(
            "a dim_municipio ainda não existe: rode `python src/main.py municipios SP`, "
            "`python src/main.py municipios-tce-sp` e `dbt run` antes de carregar despesas"
        ) from e
    if linha is None:
        raise ValueError(
            f"'{cidade}' não é uma cidade que o TCE-SP atende (ou a dim_municipio está desatualizada). "
            "Confira o nome (minúsculas, sem acento)."
        )
    return linha[0]


def cidades_carregadas() -> list[str]:
    # cidades que já passaram pelo load COM dados (devolvidas pelo nome que a API espera): é o que
    # o DAG atualiza quando ninguém escolhe cidade. Payload vazio fica de fora: a capital (TCM-SP)
    # está no raw só com [] de um teste antigo, e incluí-la faria a extração falhar todo mês pela
    # trava de "vazio". O slug vem da dimensão; sem slug (cidade que o TCE-SP não atende) não entra.
    with conectar() as conn:
        linhas = conn.execute(
            "SELECT DISTINCT m.slug_tce_sp FROM raw_pagamentos r "
            "JOIN dim_municipio m ON m.codigo_municipio = r.codigo_ibge "
            "WHERE jsonb_array_length(r.payload) > 0 AND m.slug_tce_sp IS NOT NULL "
            "ORDER BY 1"
        ).fetchall()
    return [linha[0] for linha in linhas]


def cidades_desconhecidas(cidades: list[str]) -> list[str]:
    # as que não existem em dim_municipio.slug_tce_sp, ou seja, que o TCE-SP não atende
    with conectar() as conn:
        validas = {
            linha[0]
            for linha in conn.execute(
                "SELECT slug_tce_sp FROM dim_municipio WHERE slug_tce_sp IS NOT NULL"
            ).fetchall()
        }
    return [c for c in cidades if c not in validas]
