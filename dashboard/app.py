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

df = carregar_mart()

cidade = st.sidebar.selectbox("Cidade", sorted(df["cidade"].unique()))
filtrado = df[df["cidade"] == cidade]

col_empenho, col_liquidado, col_pago = st.columns(3)
for coluna, rotulo, titulo in (
    (col_empenho, "empenhado_liquido", "Empenhado (líquido)"),
    (col_liquidado, "liquidado", "Liquidado"),
    (col_pago, "pago", "Pago"),
):
    total = filtrado[rotulo].sum()
    coluna.metric(titulo, brl_compacto(total), help=f"Valor exato: {brl(total)}")

st.dataframe(filtrado, width="stretch", hide_index=True)
