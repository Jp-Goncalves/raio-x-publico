import json
from pathlib import Path

from psycopg.types.json import Jsonb

from db import conectar

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def ler_raw(cidade: str, ano: int, mes: int) -> list:
    caminho = RAW_DIR / f"{cidade}_{ano}_{mes:02d}.json"
    with caminho.open(encoding="utf-8") as f:
        return json.load(f)


def carregar(cidade: str, ano: int, mes: int) -> None:
    dados = ler_raw(cidade, ano, mes)
    periodo = f"{ano:04d}-{mes:02d}"

    with conectar() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO raw_pagamentos (cidade, periodo, payload)
                VALUES (%s, %s, %s)
                ON CONFLICT (cidade, periodo) DO UPDATE
                    SET payload = EXCLUDED.payload,
                        extracted_at = NOW();
                """,
                (cidade, periodo, Jsonb(dados)),
            )

    print(f"{len(dados)} registros carregados para {cidade}/{periodo}")
