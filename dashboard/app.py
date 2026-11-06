import sys
from calendar import monthrange
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

# reaproveita a conexão do pipeline em vez de duplicar (src/db.py lê o .env)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from db import conectar  # noqa: E402

COLUNAS_VALOR = ["empenhado_liquido", "liquidado", "pago"]

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


def numero_br(valor: float, casas: int = 2) -> str:
    # 1234567.8 -> "1.234.567,80"
    return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def brl(valor: float) -> str:
    return "R$ " + numero_br(valor)


def brl_compacto(valor: float) -> str:
    # valores de bilhões não cabem inteiros numa métrica: 5682645088.87 -> "R$ 5,68 bi"
    if abs(valor) >= 1e9:
        return f"R$ {numero_br(valor / 1e9)} bi"
    if abs(valor) >= 1e6:
        return f"R$ {numero_br(valor / 1e6)} mi"
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

# nomes de exibição (a API usa minúsculas sem acento); cidade nova cai no .title()
NOMES = {"jacarei": "Jacareí", "campinas": "Campinas"}


def nome_cidade(cidade: str) -> str:
    return NOMES.get(cidade, cidade.title())


df = carregar_mart()

# --- filtros (barra lateral): cada widget devolve o valor escolhido no rerun atual ---
cidades_sel = st.sidebar.multiselect(
    "Cidades",
    sorted(df["cidade"].unique()),
    default=sorted(df["cidade"].unique()),
    format_func=nome_cidade,
)
if not cidades_sel:
    st.warning("Selecione ao menos uma cidade na barra lateral.")
    st.stop()  # interrompe o script aqui: nada abaixo é desenhado
das_cidades = df[df["cidade"].isin(cidades_sel)]

# os dados são mensais ('AAAA-MM'); o calendário vai do 1º dia do primeiro mês ao último do último
primeiro = date.fromisoformat(das_cidades["periodo"].min() + "-01")
ultimo_ano, ultimo_mes = map(int, das_cidades["periodo"].max().split("-"))
ultimo = date(ultimo_ano, ultimo_mes, monthrange(ultimo_ano, ultimo_mes)[1])
intervalo = st.sidebar.date_input(
    "Período",
    value=(primeiro, ultimo),
    min_value=primeiro,
    max_value=ultimo,
    format="DD/MM/YYYY",
    help="Os dados são mensais: vale cada mês que o intervalo toca.",
)
if len(intervalo) != 2:  # com o calendário aberto, o usuário já clicou só na data inicial
    st.info("Escolha também a data final no calendário.")
    st.stop()
periodo_ini, periodo_fim = (d.strftime("%Y-%m") for d in intervalo)

orgaos = sorted(das_cidades["orgao"].unique())
orgaos_sel = st.sidebar.multiselect("Órgãos", orgaos, default=orgaos)

# 'AAAA-MM' em texto ordena igual a data, então comparar strings funciona
filtrado = das_cidades[
    das_cidades["periodo"].between(periodo_ini, periodo_fim)
    & das_cidades["orgao"].isin(orgaos_sel)
]

if filtrado.empty:
    st.warning("Nenhum dado para os filtros escolhidos. Selecione ao menos um órgão.")
    st.stop()

st.caption("Cidades: " + ", ".join(nome_cidade(c) for c in cidades_sel) + " (valores somados).")

# --- métricas ---
for coluna, campo in zip(st.columns(3), ROTULOS):
    total = filtrado[campo].sum()
    coluna.metric(ROTULOS[campo], brl_compacto(total), help=f"Valor exato: {brl(total)}")

# --- gráficos ---
st.subheader("Evolução mensal")
st.caption("Uma linha por etapa do gasto. As linhas não se somam: são o mesmo dinheiro em momentos diferentes.")
evolucao = filtrado.groupby("periodo")[COLUNAS_VALOR].sum().rename(columns=ROTULOS)
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
