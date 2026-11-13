import json
from pathlib import Path

from psycopg.types.json import Jsonb

from db import conectar
from municipios import codigo_ibge_da_cidade
from validacao import validar_cidade, validar_periodo

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def ler_raw(cidade: str, ano: int, mes: int) -> list:
    # a cidade entra no nome do arquivo lido: sem isso, "../../x" leria fora de data/raw
    validar_cidade(cidade)
    validar_periodo(ano, mes)
    caminho = RAW_DIR / f"{cidade}_{ano}_{mes:02d}.json"
    with caminho.open(encoding="utf-8") as f:
        return json.load(f)


def carregar(cidade: str, ano: int, mes: int) -> None:
    dados = ler_raw(cidade, ano, mes)
    periodo = f"{ano:04d}-{mes:02d}"
    # o raw é identificado pelo código IBGE; o nome (slug) só serve pra achar o arquivo e a API
    codigo_ibge = codigo_ibge_da_cidade(cidade)

    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO raw_pagamentos (codigo_ibge, periodo, payload)
                VALUES (%s, %s, %s)
                ON CONFLICT (codigo_ibge, periodo) DO UPDATE
                    SET payload = EXCLUDED.payload,
                        extracted_at = NOW();
                """,
                (codigo_ibge, periodo, Jsonb(dados)),
            )

    print(f"{len(dados)} registros carregados para {cidade}/{periodo}")
