import json
from pathlib import Path

from api_client import get_json

API_BASE_URL = "https://transparencia.tce.sp.gov.br/api/json/despesas"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def buscar_despesas(cidade: str, ano: int, mes: int) -> list:
    url = f"{API_BASE_URL}/{cidade}/{ano}/{mes}"
    return get_json(url, f"{cidade}/{ano}/{mes}")


def salvar_raw(dados: list, cidade: str, ano: int, mes: int) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    caminho = RAW_DIR / f"{cidade}_{ano}_{mes:02d}.json"
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
    return caminho


def extrair(cidade: str, ano: int, mes: int, falhar_se_vazio: bool = False) -> Path:
    dados = buscar_despesas(cidade, ano, mes)

    if not dados and falhar_se_vazio:
        # nada é gravado: um [] não pode sobrescrever (via UPSERT no load) um raw bom
        raise ValueError(
            f"nenhum registro para {cidade}/{ano}/{mes}: a fonte pode ainda não ter "
            f"publicado esse período"
        )

    if not dados:
        print(f"[aviso] nenhum registro para {cidade}/{ano}/{mes} "
              f"(cidade fora da jurisdição do TCE-SP ou sem despesas no período)")
    else:
        print(f"{len(dados)} registros recebidos para {cidade}/{ano}/{mes}")

    caminho = salvar_raw(dados, cidade, ano, mes)
    print(f"salvo em {caminho}")
    return caminho
