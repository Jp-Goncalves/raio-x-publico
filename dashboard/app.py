import sys
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

df = carregar_mart()

# --- filtros (barra lateral): cada widget devolve o valor escolhido no rerun atual ---
cidade = st.sidebar.selectbox("Cidade", sorted(df["cidade"].unique()))
da_cidade = df[df["cidade"] == cidade]

periodos = sorted(da_cidade["periodo"].unique())
if len(periodos) > 1:
    periodo_ini, periodo_fim = st.sidebar.select_slider(
        "Período", options=periodos, value=(periodos[0], periodos[-1])
    )
else:
    periodo_ini = periodo_fim = periodos[0]

orgaos = sorted(da_cidade["orgao"].unique())
orgaos_sel = st.sidebar.multiselect("Órgãos", orgaos, default=orgaos)

# 'AAAA-MM' em texto ordena igual a data, então comparar strings funciona
filtrado = da_cidade[
    da_cidade["periodo"].between(periodo_ini, periodo_fim)
    & da_cidade["orgao"].isin(orgaos_sel)
]

if filtrado.empty:
    st.warning("Nenhum dado para os filtros escolhidos. Selecione ao menos um órgão.")
    st.stop()  # interrompe o script aqui: nada abaixo é desenhado

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
st.caption("Total pago no período escolhido.")
por_orgao = filtrado.groupby("orgao")["pago"].sum().sort_values(ascending=False)
st.bar_chart(por_orgao, horizontal=True)

# --- tabela: o Styler formata só a exibição; os números continuam ordenáveis ---
st.subheader("Detalhe")
tabela = filtrado.drop(columns="cidade").rename(
    columns={**ROTULOS, "qtd_lancamentos": "Lançamentos", "periodo": "Período", "orgao": "Órgão"}
)
formatos = {rotulo: brl for rotulo in ROTULOS.values()}
st.dataframe(
    tabela.style.format(formatos),
    width="stretch",
    hide_index=True,
    # sem limite, o nome longo do órgão empurra os valores pra fora da tela
    column_config={"Órgão": st.column_config.TextColumn(width="medium")},
)
