"""Despesas públicas mensais (TCE-SP): extract e load por cidade e mês, depois dbt run e dbt test.

Cada tarefa chama o mesmo main.py do projeto, pelo venv isolado da imagem, então
a lógica fica num lugar só.

Execução agendada (todo dia 1º, 06:00 de São Paulo): processa o mês de TRÊS
MESES ANTES da execução (MESES_DE_DEFASAGEM). O TCE-SP publica com atraso: em
06/11/2026, Jacareí e Campinas tinham setembro, mas outubro e novembro vinham
vazios. Com "mês anterior", o DAG de 1º de dezembro pediria novembro e falharia.
Execução manual: o formulário de parâmetros permite escolher as cidades (uma ou mais),
o mês inicial (AAAA-MM) e quantos meses processar a partir dele.

Não há lista fixa de cidades: as escolhidas são validadas contra a dimensão (só vale cidade que o
TCE-SP atende) e, se nenhuma for escolhida, o DAG atualiza as cidades que já foram carregadas.

Mês sem dado na fonte:
- execução AGENDADA: a extração falha e tenta de novo no dia seguinte (até 3 vezes), porque o
  TCE-SP publica com atraso e o mês costuma aparecer depois;
- execução MANUAL ou sob demanda (dashboard): a tarefa é PULADA na hora (não falha, não espera),
  porque quem pediu o mês quer a resposta agora. As outras combinações do pedido seguem.
O dbt run espera todas as extrações terminarem e roda se ao menos uma deu certo: uma combinação
sem dado (ou que falhou) não pode esconder o que as outras carregaram.
"""
import json
import shlex
import subprocess
from datetime import timedelta

import pendulum
from airflow.sdk import Param, dag, task, task_group
from airflow.timetables.interval import CronDataIntervalTimetable

VENV_BIN = "/home/airflow/project-venv/bin"
PROJETO = "/opt/airflow/project"
MAIN = f"{PROJETO}/src/main.py"
DBT_DIR = f"{PROJETO}/dbt"

# quantos meses antes da execução fica o período processado quando o mês inicial vem vazio
MESES_DE_DEFASAGEM = 3


def modo_se_vazio(run_type) -> str:
    """O que a extração faz quando a fonte não tem dado: "falhar" (agendada, tenta de novo) ou "pular"."""
    valor = str(getattr(run_type, "value", run_type))
    return "falhar" if valor == "scheduled" else "pular"


def resolver_cidades(selecionadas: list[str]) -> list[str]:
    """Pede ao main.py (a lógica fica num lugar só) a lista final de cidades.

    Valida as escolhidas contra a dimensão; sem nenhuma, devolve as já carregadas.
    O "--" garante que um valor nunca seja lido como opção.
    """
    resultado = subprocess.run(
        [f"{VENV_BIN}/python", MAIN, "cidades", "--", *selecionadas],
        capture_output=True,
        text=True,
    )
    saida = (resultado.stdout or "").strip()
    if resultado.returncode != 0:
        raise ValueError(saida or (resultado.stderr or "").strip() or "falha ao resolver as cidades")
    return json.loads(saida.splitlines()[-1])


@dag(
    dag_id="despesas_mensais",
    schedule=CronDataIntervalTimetable("0 6 1 * *", timezone="America/Sao_Paulo"),
    start_date=pendulum.datetime(2020, 1, 1, tz="America/Sao_Paulo"),
    catchup=False,  # histórico é sob demanda (backfill), não automático
    max_active_runs=1,
    params={
        "cidades": Param(
            [],
            type="array",
            items={"type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$"},
            description=(
                "Cidades a processar, uma ou mais (minúsculas, sem acento, como a API espera). "
                "Vazio = as cidades que já foram carregadas."
            ),
        ),
        "mes_inicial": Param(
            "",
            type="string",
            pattern=r"^(\d{4}-(0[1-9]|1[0-2]))?$",
            description=(
                "Primeiro mês, no formato AAAA-MM. Vazio = "
                f"{MESES_DE_DEFASAGEM} meses antes da execução (a fonte publica com atraso)."
            ),
        ),
        "quantidade_de_meses": Param(
            1,
            type="integer",
            minimum=1,
            maximum=24,
            description="Quantos meses processar a partir do mês inicial.",
        ),
    },
    tags=["raio-x-publico"],
    doc_md=__doc__,
)
def despesas_mensais():
    @task
    def montar_periodos(**context) -> list[dict]:
        params = context["params"]

        if params["mes_inicial"]:
            ano, mes = (int(parte) for parte in params["mes_inicial"].split("-"))
        else:
            dag_run = context["dag_run"]
            referencia = dag_run.data_interval_end or dag_run.run_after
            # meses desde o ano 0, base zero: dezembro/2026 menos 3 = setembro/2026
            ano, mes_zero_based = divmod(
                referencia.year * 12 + (referencia.month - 1) - MESES_DE_DEFASAGEM, 12
            )
            mes = mes_zero_based + 1

        cidades = resolver_cidades(params["cidades"])
        se_vazio = modo_se_vazio(context["dag_run"].run_type)

        periodos = []
        for deslocamento in range(params["quantidade_de_meses"]):
            ano_do_periodo, mes_zero_based = divmod(ano * 12 + (mes - 1) + deslocamento, 12)
            for cidade in cidades:
                periodos.append(
                    {"cidade": cidade, "ano": ano_do_periodo, "mes": mes_zero_based + 1, "se_vazio": se_vazio}
                )
        return periodos

    @task_group
    def processar(periodo):
        # extract: poucas chamadas simultâneas à API pública. Sem dado na fonte: agendada falha
        # sem gravar e tenta de novo no dia seguinte; manual/sob demanda é PULADA (saída 99 do
        # main.py, que o BashOperator trata como "skipped") e o load dela é pulado junto
        @task.bash(
            retries=3,
            retry_delay=timedelta(days=1),
            max_active_tis_per_dag=2,
            skip_on_exit_code=99,
        )
        def extract(periodo: dict) -> str:
            cidade = shlex.quote(periodo["cidade"])
            flag = "--falhar-se-vazio" if periodo["se_vazio"] == "falhar" else "--pular-se-vazio"
            return f"{VENV_BIN}/python {MAIN} extract {cidade} {periodo['ano']} {periodo['mes']} {flag}"

        @task.bash(retries=1, retry_delay=timedelta(minutes=5))
        def load(periodo: dict) -> str:
            cidade = shlex.quote(periodo["cidade"])
            return f"{VENV_BIN}/python {MAIN} load {cidade} {periodo['ano']} {periodo['mes']}"

        extract(periodo) >> load(periodo)

    # o dbt trabalha sobre o projeto inteiro: roda uma vez, depois de todas as cidades.
    # all_done: espera todas terminarem, em qualquer estado, e roda. Com o padrão (all_success),
    # uma combinação sem dado ou que falhou esconderia o que as outras carregaram. Também não
    # serve all_done_min_one_success (qualquer tarefa pulada faz esta ser pulada) nem
    # none_failed_min_one_success (uma falha de verdade bloquearia o dbt).
    @task.bash(retries=1, retry_delay=timedelta(minutes=5), trigger_rule="all_done")
    def dbt_run() -> str:
        return f"cd {DBT_DIR} && {VENV_BIN}/dbt run"

    @task.bash
    def dbt_test() -> str:
        return f"cd {DBT_DIR} && {VENV_BIN}/dbt test"

    # Como o dbt roda mesmo com falhas antes dele, a execução terminaria em "success" escondendo o
    # erro (o estado de uma execução vem das últimas tarefas). Esta tarefa só roda se algo falhou
    # e falha de propósito, pra execução aparecer como falha. Tarefa PULADA (mês sem dado) não conta.
    @task(trigger_rule="one_failed", retries=0)
    def conferir() -> None:
        raise RuntimeError("alguma etapa falhou: veja as tarefas em vermelho; o dbt rodou com o que deu certo")

    periodos = montar_periodos()
    carga = processar.expand(periodo=periodos)
    carga >> dbt_run() >> dbt_test()
    [periodos, carga] >> conferir()


despesas_mensais()
