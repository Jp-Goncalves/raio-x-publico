import json
import time
from pathlib import Path

import requests

API_BASE_URL = "https://transparencia.tce.sp.gov.br/api/json/despesas"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

MAX_TENTATIVAS = 4
ESPERA_BASE_SEGUNDOS = 2


def buscar_despesas(cidade: str, ano: int, mes: int) -> list:
    url = f"{API_BASE_URL}/{cidade}/{ano}/{mes}"

    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            response = requests.get(url, timeout=30)
            if response.status_code < 500:
                response.raise_for_status()  # 4xx: erro nosso, explode sem retry (except abaixo)
                return response.json()       # corpo inválido cai no except de baixo, COM retry
            print(f"[tentativa {tentativa}/{MAX_TENTATIVAS}] servidor respondeu {response.status_code}")
        except requests.exceptions.HTTPError:
            raise  # 4xx: não adianta tentar de novo, propaga na hora
        except requests.exceptions.RequestException as e:
            # conexão, timeout, ou 200 com corpo que não é JSON válido - todos transitórios
            print(f"[tentativa {tentativa}/{MAX_TENTATIVAS}] falha: {e}")

        if tentativa < MAX_TENTATIVAS:
            espera = ESPERA_BASE_SEGUNDOS * (2 ** (tentativa - 1))
            print(f"aguardando {espera}s antes de tentar de novo...")
            time.sleep(espera)

    raise RuntimeError(f"API indisponível após {MAX_TENTATIVAS} tentativas: {cidade}/{ano}/{mes}")


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
