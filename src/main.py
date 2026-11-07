import argparse
import json
import sys

from backfill import rodar_backfill
from extract import SemDadosNaFonte, extrair
from load import carregar
from municipios import (
    carregar_municipios,
    carregar_municipios_tce_sp,
    cidades_carregadas,
    cidades_desconhecidas,
)
from pipeline import rodar_pipeline
from transform import transformar_e_gravar


# o Airflow (BashOperator) marca a tarefa como "pulada", e não como falha, quando ela sai com 99
CODIGO_SAIDA_SEM_DADOS = 99


def _add_cidade_ano_mes(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("cidade")
    subparser.add_argument("ano", type=int)
    subparser.add_argument("mes", type=int)


def imprimir_cidades(informadas: list[str]) -> None:
    """Imprime em JSON a lista de cidades a processar (a última linha da saída é a lista).

    Com cidades informadas, valida contra a dimensão (erro se o TCE-SP não atender alguma).
    Sem nenhuma, devolve as cidades que já foram carregadas; vazio é erro, pra um agendamento
    não "passar" sem processar nada.
    """
    if informadas:
        desconhecidas = cidades_desconhecidas(informadas)
        if desconhecidas:
            raise ValueError(
                f"cidades que o TCE-SP não atende (ou fora da dimensão): {', '.join(desconhecidas)}. "
                f"Confira o nome (minúsculas, sem acento) e se `dbt run` já montou dim_municipio."
            )
        cidades = informadas
    else:
        cidades = cidades_carregadas()
        if not cidades:
            raise ValueError("nenhuma cidade informada e nenhuma carregada ainda: escolha ao menos uma")
    print(json.dumps(cidades))


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline raio-x-publico")
    subparsers = parser.add_subparsers(dest="comando", required=True)

    p_extract = subparsers.add_parser("extract", help="só extrai da API e salva o raw")
    _add_cidade_ano_mes(p_extract)
    p_extract.add_argument(
        "--falhar-se-vazio",
        action="store_true",
        help="falha (sem gravar nada) se a API devolver zero registros",
    )
    p_extract.add_argument(
        "--pular-se-vazio",
        action="store_true",
        help=(
            f"se a API devolver zero registros, não grava nada e sai com o código {CODIGO_SAIDA_SEM_DADOS}, "
            "que o Airflow trata como tarefa pulada (não como falha)"
        ),
    )
    _add_cidade_ano_mes(subparsers.add_parser("load", help="só carrega o raw salvo no Postgres"))
    _add_cidade_ano_mes(subparsers.add_parser("transform", help="só transforma e grava em stg_pagamentos"))
    _add_cidade_ano_mes(subparsers.add_parser("pipeline", help="roda extract -> load -> transform"))
    p_backfill = subparsers.add_parser(
        "backfill", help="roda o pipeline pros 12 meses de um ano, pra uma ou mais cidades"
    )
    p_backfill.add_argument("ano", type=int)
    p_backfill.add_argument("cidades", nargs="+", help="uma ou mais cidades (slug)")
    p_municipios = subparsers.add_parser(
        "municipios", help="carrega os municípios de uma UF (API do IBGE) em raw_ibge_municipios"
    )
    p_municipios.add_argument("uf", help="sigla da UF, ex.: SP")
    p_cidades = subparsers.add_parser(
        "cidades",
        help="imprime (JSON) as cidades a processar: as informadas, validadas, ou as já carregadas",
    )
    p_cidades.add_argument("cidades", nargs="*", help="slugs; sem nenhum, usa as cidades já carregadas")
    subparsers.add_parser(
        "municipios-tce-sp",
        help="carrega a lista de municípios que o TCE-SP atende em raw_tce_sp_municipios",
    )

    args = parser.parse_args()

    try:
        if args.comando == "extract":
            extrair(
                args.cidade,
                args.ano,
                args.mes,
                falhar_se_vazio=args.falhar_se_vazio,
                pular_se_vazio=args.pular_se_vazio,
            )
        elif args.comando == "load":
            carregar(args.cidade, args.ano, args.mes)
        elif args.comando == "transform":
            transformar_e_gravar(args.cidade, args.ano, args.mes)
        elif args.comando == "pipeline":
            rodar_pipeline(args.cidade, args.ano, args.mes)
        elif args.comando == "backfill":
            rodar_backfill(args.cidades, args.ano)
        elif args.comando == "municipios":
            carregar_municipios(args.uf)
        elif args.comando == "municipios-tce-sp":
            carregar_municipios_tce_sp()
        elif args.comando == "cidades":
            imprimir_cidades(args.cidades)
    except SemDadosNaFonte as e:
        print(f"\n[sem dados] {e}")
        sys.exit(CODIGO_SAIDA_SEM_DADOS)
    except Exception as e:
        print(f"\n[erro] comando '{args.comando}' falhou: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
