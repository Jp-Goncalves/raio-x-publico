import sys
from calendar import monthrange
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

# reaproveita a conexão do pipeline em vez de duplicar (src/db.py lê o .env)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from airflow_client import AirflowIndisponivel, dag_pausado, disparar_carga, estado_da_carga  # noqa: E402
from db import conectar  # noqa: E402

COLUNAS_VALOR = ["empenhado_liquido", "liquidado", "pago"]

# limites de um pedido de carga sob demanda: sem eles, o "Select all" (644 cidades) ou um
# calendário de anos disparariam milhares de chamadas à API pública de uma vez
LIMITE_CIDADES_POR_PEDIDO = 5
LIMITE_MESES_POR_PEDIDO = 12

# a fonte publica com atraso: o filtro abre N meses antes de hoje (mesmo valor do DAG,
# MESES_DE_DEFASAGEM em airflow/dags/despesas_mensais.py)
MESES_DE_DEFASAGEM = 3
# primeiro mês com dado na fonte (medido em Jacareí: 2013 vem vazio, 2014-01 tem; outras
# cidades podem começar depois)
PRIMEIRO_MES_DA_FONTE = date(2014, 1, 1)

st.set_page_config(page_title="Raio-X Público", layout="wide")


# o Streamlit roda este script inteiro a cada clique; o cache evita refazer a query
@st.cache_data(ttl=300)
def carregar_mart() -> pd.DataFrame:
    with conectar() as conn:
        cur = conn.execute(
            "select cidade, periodo, orgao, empenhado_liquido, liquidado, pago, qtd_lancamentos "
            "from fct_despesas_mensais order by cidade, periodo, orgao"
        )
        colunas = [c.name for c in cur.description]
        linhas = cur.fetchall()
    df = pd.DataFrame(linhas, columns=colunas)
    df[COLUNAS_VALOR] = df[COLUNAS_VALOR].astype(float)  # o banco devolve Decimal
    return df


@st.cache_data(ttl=300)
def carregar_localidades() -> pd.DataFrame:
    # só os municípios que o TCE-SP atende (slug_tce_sp preenchido): os outros nunca
    # terão despesa nessa fonte, então não faz sentido oferecê-los
    with conectar() as conn:
        cur = conn.execute(
            "select e.uf, e.nome_uf, m.nome_municipio, m.slug_tce_sp "
            "from dim_municipio m join dim_estado e using (uf) "
            "where m.slug_tce_sp is not null order by e.uf, m.nome_municipio"
        )
        colunas = [c.name for c in cur.description]
        linhas = cur.fetchall()
    return pd.DataFrame(linhas, columns=colunas)


def mes_de_defasagem(hoje: date) -> tuple[date, date]:
    # primeiro e último dia do mês que fica MESES_DE_DEFASAGEM antes de hoje
    ano, mes_zero_based = divmod(hoje.year * 12 + (hoje.month - 1) - MESES_DE_DEFASAGEM, 12)
    mes = mes_zero_based + 1
    return date(ano, mes, 1), date(ano, mes, monthrange(ano, mes)[1])


def numero_br(valor: float, casas: int = 2) -> str:
    # 1234567.8 -> "1.234.567,80"
    return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def brl(valor: float) -> str:
    return "R$ " + numero_br(valor)


def _tres_digitos(valor: float) -> str:
    # 3 dígitos significativos: 123.38 -> "123", 65.15 -> "65,2", 5.68 -> "5,68"
    casas = 0 if abs(valor) >= 100 else 1 if abs(valor) >= 10 else 2
    return numero_br(valor, casas)


def brl_compacto(valor: float) -> str:
    # valores grandes não cabem inteiros numa métrica (a coluna corta o texto):
    # 5682645088.87 -> "R$ 5,68 bi"; o valor exato fica no balão de ajuda
    if abs(valor) >= 1e9:
        return f"R$ {_tres_digitos(valor / 1e9)} bi"
    if abs(valor) >= 1e6:
        return f"R$ {_tres_digitos(valor / 1e6)} mi"
    return brl(valor)


st.title("Raio-X Público")
st.caption(
    "Despesas municipais do TCE-SP. Empenho, liquidação e pagamento são etapas do "
    "mesmo gasto, por isso aparecem separados e nunca somados entre si."
)

ROTULOS = {
    "empenhado_liquido": "Empenhado (líquido)",
    "liquidado": "Liquidado",
    "pago": "Pago",
}

df = carregar_mart()
localidades = carregar_localidades()
if localidades.empty:
    st.error(
        "A lista de municípios está vazia. Rode `python src/main.py municipios SP` e "
        "`python src/main.py municipios-tce-sp`, depois `dbt run`."
    )
    st.stop()

# --- filtros (barra lateral) ---
# o filtro de estado nasce dos dados: só aparece estado com município atendido pela fonte.
# Fica FORA do formulário: as cidades dependem dele e precisam mudar na hora
estados = localidades.drop_duplicates("uf").set_index("uf")["nome_uf"]
uf = st.sidebar.selectbox("Estado", list(estados.index), format_func=lambda u: f"{estados[u]} ({u})")
do_estado = localidades[localidades["uf"] == uf]
nomes = dict(zip(do_estado["slug_tce_sp"], do_estado["nome_municipio"]))  # slug -> nome de exibição
com_dados = set(df["cidade"])


def nome_cidade(slug: str) -> str:
    return nomes.get(slug, slug.title())


def rotulo_cidade(slug: str) -> str:
    return nome_cidade(slug) + (" ✓" if slug in com_dados else "")


def resumo_nomes(nomes_: list[str], limite: int = 5) -> str:
    # o "Select all" pode trazer centenas de cidades sem dado: não despeja todos os nomes na tela
    if len(nomes_) <= limite:
        return ", ".join(nomes_)
    return ", ".join(nomes_[:limite]) + f" e mais {len(nomes_) - limite}"


# quem tem dado carregado vem primeiro; o resto, em ordem alfabética
opcoes = sorted(nomes, key=lambda slug: (slug not in com_dados, nomes[slug]))
hoje = date.today()
inicio_padrao, fim_padrao = mes_de_defasagem(hoje)

# O que já foi confirmado volta como valor inicial dos filtros. Sem isso, quando a carga termina
# os municípios novos ganham ✓ e sobem pro topo da lista; com as opções em outra ordem, o
# Streamlit trata o filtro como um widget novo e o zera, e a pessoa perderia as cidades escolhidas.
anterior = st.session_state.get("aplicado")
if anterior and anterior["uf"] == uf:
    cidades_iniciais = [c for c in anterior["cidades"] if c in nomes]
    periodo_inicial = anterior["intervalo"]
else:
    cidades_iniciais = []  # primeira vez: abre sem nenhuma cidade, quem usa escolhe
    periodo_inicial = (inicio_padrao, fim_padrao)

# com uma carga em andamento, o botão fica travado: sem isso, cada clique a mais seria um pedido
carga_atual = st.session_state.get("carga")
carregando = bool(carga_atual and carga_atual.get("fase") == "andamento")

# dentro do formulário, mexer nos widgets não refaz a tela: só o botão Confirmar aplica
with st.sidebar.form("filtros"):
    cidades_sel = st.multiselect(
        "Cidades",
        opcoes,
        default=cidades_iniciais,
        format_func=rotulo_cidade,
        placeholder="Escolha uma ou mais cidades",
        help="✓ = município com dados carregados.",
    )
    intervalo = st.date_input(
        "Período",
        value=periodo_inicial,
        min_value=PRIMEIRO_MES_DA_FONTE,
        max_value=hoje,
        format="DD/MM/YYYY",
        help=(
            f"Abre {MESES_DE_DEFASAGEM} meses antes de hoje, porque a fonte publica com atraso. "
            "Os dados são mensais: vale cada mês que o intervalo toca."
        ),
    )
    if carregando:
        st.caption("⏳ Carga em andamento. Aguarde para confirmar de novo.")
    confirmar = st.form_submit_button("Confirmar", type="primary", width="stretch", disabled=carregando)

# o botão só devolve True no clique; o que foi confirmado fica guardado entre as interações
if confirmar:
    if len(intervalo) != 2:  # com o calendário aberto, o usuário já clicou só na data inicial
        st.sidebar.warning("Escolha também a data final no calendário.")
    elif not cidades_sel:
        st.sidebar.warning("Escolha ao menos uma cidade.")
    else:
        st.session_state["aplicado"] = {"uf": uf, "cidades": list(cidades_sel), "intervalo": tuple(intervalo)}

aplicado = st.session_state.get("aplicado")
if aplicado and aplicado["uf"] != uf:  # trocou de estado: o que estava confirmado era de outro
    st.session_state.pop("aplicado")
    aplicado = None
if not aplicado:
    st.info("Escolha as cidades e o período na barra lateral e clique em Confirmar. As cidades com ✓ têm dados carregados.")
    st.stop()  # interrompe o script aqui: nada abaixo é desenhado



def meses_do_intervalo(inicio: str, fim: str) -> list[str]:
    # 'AAAA-MM' de inicio a fim, inclusive
    ano, mes = map(int, inicio.split("-"))
    ano_fim, mes_fim = map(int, fim.split("-"))
    meses = []
    while (ano, mes) <= (ano_fim, mes_fim):
        meses.append(f"{ano:04d}-{mes:02d}")
        ano, mes = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return meses


# o Streamlit refaz o script a cada interação; este fragmento se refaz sozinho a cada 5 s
# (e só ele), consultando o andamento da carga sem recarregar a tela toda
@st.fragment(run_every="5s")
def acompanhar_carga(run_id: str, descricao: str) -> None:
    # fases da carga em st.session_state["carga"]["fase"]: andamento -> concluida | falhou | parada.
    # Quando a fase muda, a página INTEIRA é refeita (st.rerun), pra o botão Confirmar destravar.
    try:
        estado = estado_da_carga(run_id)
    except AirflowIndisponivel as e:
        estado = None
        st.error(f"Perdi o contato com o Airflow: {e}.")
    if estado == "success":
        st.cache_data.clear()  # senão o dashboard seguiria mostrando a consulta antiga por 5 min
        st.session_state["carga"]["fase"] = "concluida"
        st.rerun()
    if estado == "failed":
        st.session_state["carga"]["fase"] = "falhou"
        st.rerun()
    if estado is not None:
        andamento = "na fila" if estado == "queued" else "em andamento"
        st.info(f"⏳ Carregando {descricao} ({andamento}). Esta tela atualiza sozinha quando terminar.")
    # saída pra quem não quer esperar: a carga continua no Airflow, só deixamos de acompanhá-la
    if st.button("Parar de acompanhar"):
        st.session_state["carga"]["fase"] = "parada"
        st.rerun()


def solicitar_carga(faltando: list[str], meses: list[str]) -> None:
    """Pede ao Airflow a carga do que falta, uma vez por pedido, e acompanha o andamento."""
    nomes_faltando = resumo_nomes([nome_cidade(c) for c in faltando])
    periodo = meses[0] if len(meses) == 1 else f"{meses[0]} a {meses[-1]}"
    descricao = f"{nomes_faltando} ({periodo})"
    chave = (tuple(sorted(faltando)), meses[0], len(meses))

    ultimo_pedivel = mes_de_defasagem(hoje)[1].strftime("%Y-%m")
    if meses[-1] > ultimo_pedivel:
        st.warning(
            f"Sem dados carregados para {descricao}. A fonte publica com atraso, então só peço "
            f"cargas até {ultimo_pedivel}."
        )
        return
    if len(faltando) > LIMITE_CIDADES_POR_PEDIDO:
        st.warning(
            f"{len(faltando)} cidades sem dados no período: o limite é {LIMITE_CIDADES_POR_PEDIDO} "
            "por pedido. Escolha menos cidades."
        )
        return
    if len(meses) > LIMITE_MESES_POR_PEDIDO:
        st.warning(
            f"{len(meses)} meses é mais que o limite de {LIMITE_MESES_POR_PEDIDO} por pedido. "
            "Escolha um período menor."
        )
        return

    carga = st.session_state.get("carga")
    if carga and carga["chave"] == chave:  # pedido já feito nesta sessão: não dispara de novo
        fase = carga["fase"]
        if fase == "concluida":
            st.warning(
                f"A carga terminou, mas ainda não há dados de {descricao}: a fonte pode não ter "
                "publicado esse período."
            )
        elif fase == "falhou":
            st.error(
                f"A carga de {descricao} falhou. Pode ser que a fonte ainda não tenha publicado esse "
                "período, ou que a cidade não tenha dado nele. Os detalhes estão no Airflow "
                "(http://127.0.0.1:8080)."
            )
            if st.button("Tentar de novo"):
                st.session_state.pop("carga", None)
                st.rerun()
        elif fase == "parada":
            st.info(
                f"Você parou de acompanhar a carga de {descricao}. Ela continua no Airflow e, quando "
                "terminar, o dado aparece aqui."
            )
            if st.button("Acompanhar de novo"):
                carga["fase"] = "andamento"
                st.rerun()
        else:  # andamento
            acompanhar_carga(carga["run_id"], descricao)
        return

    try:
        if dag_pausado():
            st.warning(
                f"Sem dados carregados para {descricao}. Pra carregar sob demanda, o DAG "
                "`despesas_mensais` precisa estar ativo (hoje está pausado). Ative-o na interface do "
                "Airflow (http://127.0.0.1:8080)."
            )
            return
        run_id = disparar_carga(faltando, meses[0], len(meses))
    except AirflowIndisponivel as e:
        st.error(
            f"Sem dados carregados para {descricao}, e não consegui pedir a carga: {e}. O Airflow "
            "está no ar? (`docker compose --profile airflow up -d`)"
        )
        return
    st.session_state["carga"] = {"chave": chave, "run_id": run_id, "fase": "andamento"}
    st.rerun()  # refaz a página já com a carga em andamento: o botão Confirmar nasce travado


cidades_aplicadas = aplicado["cidades"]
periodo_ini, periodo_fim = (d.strftime("%Y-%m") for d in aplicado["intervalo"])

# o que falta carregar: cidade sem algum dos meses pedidos
meses_pedidos = meses_do_intervalo(periodo_ini, periodo_fim)
carregados = df.groupby("cidade")["periodo"].agg(set).to_dict()
faltando = [c for c in cidades_aplicadas if not set(meses_pedidos) <= carregados.get(c, set())]
if faltando:
    solicitar_carga(faltando, meses_pedidos)  # mostra o aviso ou o andamento da carga

das_cidades = df[df["cidade"].isin(cidades_aplicadas)]
if das_cidades.empty:
    st.stop()  # nada pra mostrar ainda; o aviso ou o andamento da carga já está na tela

# fora do formulário: as opções dependem das cidades já confirmadas
orgaos = sorted(das_cidades["orgao"].unique())
orgaos_sel = st.sidebar.multiselect("Órgãos", orgaos, default=orgaos)

# 'AAAA-MM' em texto ordena igual a data, então comparar strings funciona
no_periodo = das_cidades[das_cidades["periodo"].between(periodo_ini, periodo_fim)]
filtrado = no_periodo[no_periodo["orgao"].isin(orgaos_sel)]

if no_periodo.empty:
    st.stop()  # sem dado no período; o aviso ou o andamento da carga já está na tela
if filtrado.empty:
    st.warning("Selecione ao menos um órgão.")
    st.stop()

st.caption("Cidades: " + ", ".join(nome_cidade(c) for c in cidades_aplicadas if c in com_dados) + " (valores somados).")

# --- métricas ---
for coluna, campo in zip(st.columns(3), ROTULOS):
    total = filtrado[campo].sum()
    coluna.metric(ROTULOS[campo], brl_compacto(total), help=f"Valor exato: {brl(total)}")

# --- gráficos ---
st.subheader("Evolução mensal")
st.caption(
    "Uma linha por etapa do gasto (barras lado a lado, se for um mês só). "
    "As etapas não se somam: são o mesmo dinheiro em momentos diferentes."
)
evolucao = filtrado.groupby("periodo")[COLUNAS_VALOR].sum().rename(columns=ROTULOS)
if len(evolucao) < 2:
    # uma linha de um ponto só não aparece: com um único mês, barras mostram as três etapas.
    # stack=False: lado a lado. Empilhadas, as barras somariam as etapas, que são o mesmo gasto.
    st.bar_chart(evolucao, stack=False)
else:
    st.line_chart(evolucao)

st.subheader("Pago por órgão")
st.caption("Total pago no período escolhido. A cor indica a cidade.")
por_orgao = (
    filtrado.assign(cidade=filtrado["cidade"].map(nome_cidade))
    .groupby(["orgao", "cidade"], as_index=False)["pago"]
    .sum()
)
st.bar_chart(por_orgao, x="orgao", y="pago", color="cidade", horizontal=True)

# --- tabela: o Styler formata só a exibição; os números continuam ordenáveis ---
st.subheader("Detalhe")
tabela = filtrado.assign(cidade=filtrado["cidade"].map(nome_cidade)).rename(
    columns={
        **ROTULOS,
        "qtd_lancamentos": "Lançamentos",
        "cidade": "Cidade",
        "periodo": "Período",
        "orgao": "Órgão",
    }
)
formatos = {rotulo: brl for rotulo in ROTULOS.values()}
st.dataframe(
    tabela.style.format(formatos),
    width="stretch",
    hide_index=True,
    # sem limite, o nome longo do órgão empurra os valores pra fora da tela
    column_config={"Órgão": st.column_config.TextColumn(width="medium")},
)
