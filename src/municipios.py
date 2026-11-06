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
