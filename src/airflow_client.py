"""Cliente mínimo da API REST do Airflow, usado pelo dashboard pra pedir cargas sob demanda.

O dashboard não grava no banco: ele só pede ao Airflow uma execução do DAG despesas_mensais,
com as cidades e o mês inicial escolhidos. Usa um usuário restrito (papel Op), não o admin.
"""
import hashlib
import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()

DAG_ID = "despesas_mensais"
TIMEOUT = 10  # segundos; o dashboard não pode travar esperando o Airflow


class AirflowIndisponivel(Exception):
    """Não deu pra falar com o Airflow (fora do ar, URL errada, credencial recusada)."""


_token_cache: dict = {"valor": None, "obtido_em": 0.0}


def _base_url() -> str:
    # no Compose é http://airflow-apiserver:8080; rodando direto na máquina, a porta publicada
    return os.environ.get("AIRFLOW_API_URL", "http://127.0.0.1:8080").rstrip("/")


def _token() -> str:
    # o token vale por horas; reaproveitar evita refazer o login a cada consulta de status
    if _token_cache["valor"] and time.time() - _token_cache["obtido_em"] < 600:
        return _token_cache["valor"]
    usuario = os.environ.get("DASHBOARD_AIRFLOW_USER")
    senha = os.environ.get("DASHBOARD_AIRFLOW_PASSWORD")
    if not usuario or not senha:
        raise AirflowIndisponivel("credenciais do Airflow não configuradas (DASHBOARD_AIRFLOW_USER/PASSWORD)")
    try:
        r = requests.post(
            f"{_base_url()}/auth/token", json={"username": usuario, "password": senha}, timeout=TIMEOUT
        )
    except requests.exceptions.RequestException as e:
        raise AirflowIndisponivel(f"sem conexão com o Airflow em {_base_url()}") from e
    if r.status_code not in (200, 201):
        raise AirflowIndisponivel(f"o Airflow recusou o login do usuário '{usuario}' (HTTP {r.status_code})")
    _token_cache.update(valor=r.json()["access_token"], obtido_em=time.time())
    return _token_cache["valor"]


def _chamar(metodo: str, caminho: str, **kwargs) -> requests.Response:
    try:
        return requests.request(
            metodo,
            f"{_base_url()}/api/v2{caminho}",
            headers={"Authorization": f"Bearer {_token()}"},
            timeout=TIMEOUT,
            **kwargs,
        )
    except requests.exceptions.RequestException as e:
        raise AirflowIndisponivel(f"sem conexão com o Airflow em {_base_url()}") from e


def id_da_carga(cidades: list[str], mes_inicial: str, quantidade: int) -> str:
    """Identificador determinístico do pedido: o mesmo pedido gera o mesmo id.

    O Airflow recusa (409) um id repetido, então dois cliques, ou duas pessoas pedindo a mesma
    coisa, não disparam duas cargas iguais.
    """
    chave = f"{','.join(sorted(cidades))}|{mes_inicial}|{quantidade}"
    return f"sob_demanda__{hashlib.sha1(chave.encode()).hexdigest()[:12]}"


def dag_pausado() -> bool:
    r = _chamar("GET", f"/dags/{DAG_ID}")
    if r.status_code != 200:
        raise AirflowIndisponivel(f"não consegui ler o DAG {DAG_ID} (HTTP {r.status_code})")
    return bool(r.json()["is_paused"])


def estado_da_carga(run_id: str) -> str:
    """queued, running, success ou failed."""
    r = _chamar("GET", f"/dags/{DAG_ID}/dagRuns/{run_id}")
    if r.status_code != 200:
        raise AirflowIndisponivel(f"não consegui ler a execução {run_id} (HTTP {r.status_code})")
    return r.json()["state"]


def disparar_carga(cidades: list[str], mes_inicial: str, quantidade: int) -> str:
    """Pede a carga e devolve o id da execução (nova, ou a que já existia pro mesmo pedido)."""
    run_id = id_da_carga(cidades, mes_inicial, quantidade)
    corpo = {
        "dag_run_id": run_id,
        "logical_date": None,
        "conf": {"cidades": sorted(cidades), "mes_inicial": mes_inicial, "quantidade_de_meses": quantidade},
        "note": "pedido pelo dashboard",
    }
    r = _chamar("POST", f"/dags/{DAG_ID}/dagRuns", json=corpo)
    if r.status_code in (200, 201):
        return run_id
    if r.status_code == 409:
        # já existe uma execução com esse id. Se falhou, vale um novo pedido (id novo);
        # se está em andamento ou deu certo, é essa mesma que vamos acompanhar.
        if estado_da_carga(run_id) == "failed":
            return disparar_carga_de_novo(corpo)
        return run_id
    raise AirflowIndisponivel(f"o Airflow recusou o pedido (HTTP {r.status_code}): {r.text[:200]}")


def disparar_carga_de_novo(corpo: dict) -> str:
    novo = {**corpo, "dag_run_id": f"{corpo['dag_run_id']}__r{int(time.time())}"}
    r = _chamar("POST", f"/dags/{DAG_ID}/dagRuns", json=novo)
    if r.status_code not in (200, 201):
        raise AirflowIndisponivel(f"o Airflow recusou o novo pedido (HTTP {r.status_code}): {r.text[:200]}")
    return novo["dag_run_id"]
