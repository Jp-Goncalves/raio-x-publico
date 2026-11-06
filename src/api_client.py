import time

import requests

MAX_TENTATIVAS = 4
ESPERA_BASE_SEGUNDOS = 2


def get_json(url: str, descricao: str):
    """GET com retry e backoff exponencial, devolvendo o JSON já lido.

    - 5xx, falha de rede, timeout e 200 com corpo que não é JSON: transitórios, tenta de novo.
    - 4xx: erro do nosso pedido, falha na hora (tentar de novo não resolve).
    `descricao` só entra nas mensagens, pra saber de qual chamada se fala.
    """
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

    raise RuntimeError(f"API indisponível após {MAX_TENTATIVAS} tentativas: {descricao}")
