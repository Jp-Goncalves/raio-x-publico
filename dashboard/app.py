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

# dentro do formulário, mexer nos widgets não refaz a tela: só o botão Confirmar aplica
with st.sidebar.form("filtros"):
    cidades_sel = st.multiselect(
        "Cidades",
        opcoes,
        default=[],  # abre sem nenhuma cidade: quem usa escolhe
        format_func=rotulo_cidade,
        placeholder="Escolha uma ou mais cidades",
        help="✓ = município com dados carregados.",
    )
    intervalo = st.date_input(
        "Período",
        value=(inicio_padrao, fim_padrao),
        min_value=PRIMEIRO_MES_DA_FONTE,
        max_value=hoje,
        format="DD/MM/YYYY",
        help=(
            f"Abre {MESES_DE_DEFASAGEM} meses antes de hoje, porque a fonte publica com atraso. "
            "Os dados são mensais: vale cada mês que o intervalo toca."
        ),
    )
    confirmar = st.form_submit_button("Confirmar", type="primary", width="stretch")

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

cidades_aplicadas = aplicado["cidades"]
periodo_ini, periodo_fim = (d.strftime("%Y-%m") for d in aplicado["intervalo"])

sem_dados = [nome_cidade(c) for c in cidades_aplicadas if c not in com_dados]
das_cidades = df[df["cidade"].isin(cidades_aplicadas)]
if das_cidades.empty:
    st.warning("Ainda não há dados carregados para: " + resumo_nomes(sem_dados) + ".")
    st.stop()
if sem_dados:
    st.info("Sem dados carregados, ficam de fora: " + resumo_nomes(sem_dados) + ".")

# fora do formulário: as opções dependem das cidades já confirmadas
orgaos = sorted(das_cidades["orgao"].unique())
orgaos_sel = st.sidebar.multiselect("Órgãos", orgaos, default=orgaos)

# 'AAAA-MM' em texto ordena igual a data, então comparar strings funciona
no_periodo = das_cidades[das_cidades["periodo"].between(periodo_ini, periodo_fim)]
filtrado = no_periodo[no_periodo["orgao"].isin(orgaos_sel)]

if no_periodo.empty:
    meses = das_cidades["periodo"].nunique()  # a contagem, não só o intervalo: pode haver buracos
    st.warning(
        f"Não há dados carregados de {periodo_ini} a {periodo_fim} para essas cidades. "
        f"Há {meses} mês(es) carregado(s), entre {das_cidades['periodo'].min()} e "
        f"{das_cidades['periodo'].max()}. A carga sob demanda ainda não existe: o DAG carrega os meses."
    )
    st.stop()
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
